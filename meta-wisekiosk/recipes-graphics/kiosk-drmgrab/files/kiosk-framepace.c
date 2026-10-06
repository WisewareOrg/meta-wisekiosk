/* Record when the scanout's marquee region changes, one sample per vblank.
 *
 *   kiosk-framepace --seconds N --out FILE
 *
 * Each sample reads the active CRTC's buffer_id and hashes the ride-name
 * marquee rows of that framebuffer: one scanline through each of 10 text rows,
 * x 70-325 and 434-688 inclusive, at 1280x720. Each framebuffer is looked up
 * with GETFB2, prime-exported and mmap'd read-only once, cached by fb id, and
 * read bracketed by DMA_BUF_IOCTL_SYNC as kiosk-drmgrab does. Needs root.
 *
 * Pacing: drmWaitVBlank (relative, 1) on the active CRTC when a probe wait
 * succeeds, else 10 ms absolute CLOCK_MONOTONIC sleeps.
 *
 * Record, streamed to FILE:
 *   H tool=<sha256 prefix>  H mode=<w>x<h>@<vrefresh>
 *   H pacing=vblank | H pacing=timer100 <reason>
 *   H regions=<x spans>;<y list>;step<k>  H start=<UTC>  H seconds=<N>
 *   S <t_ns> <fb_id> <hash16> <vblank seq | ->      one per sample
 *   H cpu_ms=<utime+stime>
 *   H samples=<n> missed=<n> end=<UTC>
 * t_ns is CLOCK_MONOTONIC just before the pixel reads; hash16 is FNV-1a 64
 * over R,G,B of every region pixel in y, span, x order. missed counts skipped
 * vblank sequences, or skipped 10 ms deadlines under the timer.
 *
 * Exit 0 on a complete record. Exit 2, writing nothing, when the CRTC mode is
 * not 1280x720. Any other failure exits 1 with the reason on stderr and no
 * footer lines.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

#include <linux/dma-buf.h>
#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#ifndef FRAMEPACE_VERSION
#error "FRAMEPACE_VERSION must be defined"
#endif

#define CARD "/dev/dri/card0"
#define MODE_W 1280
#define MODE_H 720
#define TIMER_NS 10000000u

static void fail(const char *fmt, ...) __attribute__((format(printf, 1, 2), noreturn));

static void fail(const char *fmt, ...)
{
	va_list ap;

	fputs("kiosk-framepace: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
	exit(1);
}

#include "kiosk-scanout.h"

/* region: begin */
static const uint32_t ROW_Y[] = {303, 326, 350, 388, 411, 522, 545, 568, 607, 630};
static const uint32_t SPAN_X[][2] = {{70, 325}, {434, 688}};
#define N_ROWS (sizeof(ROW_Y) / sizeof(ROW_Y[0]))
#define N_SPANS (sizeof(SPAN_X) / sizeof(SPAN_X[0]))
#define STEP 1u

/* Byte offsets of the region's pixels, in hash order; returns the count. */
static size_t region_offsets(size_t *off, int tiled, uint32_t pitch, size_t base)
{
	size_t n = 0;

	for (size_t r = 0; r < N_ROWS; r++)
		for (size_t s = 0; s < N_SPANS; s++)
			for (uint32_t x = SPAN_X[s][0]; x <= SPAN_X[s][1]; x += STEP)
				off[n++] = base + (tiled ? t_offset(x, ROW_Y[r], pitch / 128)
							 : (size_t)ROW_Y[r] * pitch + (size_t)x * 4);
	return n;
}

/* FNV-1a 64 over R, G, B of each pixel; one 32-bit load per pixel. */
static uint64_t region_hash(const uint8_t *map, const size_t *off, size_t n)
{
	uint64_t h = 0xcbf29ce484222325u;

	for (size_t i = 0; i < n; i++) {
		uint32_t v;

		memcpy(&v, map + off[i], 4);
		h = (h ^ ((v >> 16) & 0xff)) * 0x100000001b3u;
		h = (h ^ ((v >> 8) & 0xff)) * 0x100000001b3u;
		h = (h ^ (v & 0xff)) * 0x100000001b3u;
	}
	return h;
}
/* region: end */

struct fbmap {
	uint32_t id;
	int pfd;
	const uint8_t *map;
	size_t *off, n;
};

static struct fbmap *maps;
static size_t n_maps;

static uint64_t now_ns(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
}

static void utc(char *buf, size_t len)
{
	time_t t = time(NULL);
	struct tm tm;

	strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", gmtime_r(&t, &tm));
}

static int wait_vblank(int fd, uint32_t pipe, drmVBlank *v)
{
	memset(v, 0, sizeof(*v));
	v->request.type = DRM_VBLANK_RELATIVE |
			  ((pipe << DRM_VBLANK_HIGH_CRTC_SHIFT) & DRM_VBLANK_HIGH_CRTC_MASK);
	v->request.sequence = 1;
	return drmWaitVBlank(fd, v);
}

static const struct fbmap *map_fb(int fd, uint32_t id, uint32_t crtc_id)
{
	struct fbmap m = {.id = id};
	drmModeFB2Ptr fb;
	size_t len;

	for (size_t i = 0; i < n_maps; i++)
		if (maps[i].id == id)
			return &maps[i];
	fb = fb_get(fd, id, crtc_id);
	if (fb->width <= SPAN_X[N_SPANS - 1][1] || fb->height <= ROW_Y[N_ROWS - 1])
		fail("fb %u is %ux%u, smaller than the region", id, fb->width, fb->height);
	m.map = fb_map(fd, fb, &m.pfd, &len);
	m.off = malloc(sizeof(*m.off) * N_ROWS * MODE_W);
	maps = realloc(maps, sizeof(*maps) * (n_maps + 1));
	if (!m.off || !maps)
		fail("out of memory");
	m.n = region_offsets(m.off, fb->modifier == DRM_FORMAT_MOD_BROADCOM_VC4_T_TILED,
			     fb->pitches[0], fb->offsets[0]);
	drmCloseBufferHandle(fd, fb->handles[0]);
	drmModeFreeFB2(fb);
	maps[n_maps] = m;
	return &maps[n_maps++];
}

int main(int argc, char **argv)
{
	uint32_t crtc_id = 0, pipe = 0, seconds = 0, vrefresh = 0, prev_seq = 0;
	uint64_t t, t_end, deadline, samples = 0, missed = 0;
	const char *out_path = NULL;
	char when[32], reason[160] = "", seq[16] = "-";
	struct dma_buf_sync sync;
	drmModeCrtcPtr crtc;
	struct rusage ru;
	drmVBlank vbl;
	int fd, vblank, w = 0, h = 0;
	FILE *out;

	for (int i = 1; i + 1 < argc; i += 2) {
		char *e;

		if (!strcmp(argv[i], "--seconds")) {
			unsigned long v = strtoul(argv[i + 1], &e, 10);

			if (*e || !*argv[i + 1] || v == 0 || v > UINT32_MAX)
				fail("bad --seconds '%s'", argv[i + 1]);
			seconds = v;
		} else if (!strcmp(argv[i], "--out")) {
			out_path = argv[i + 1];
		} else {
			break;
		}
	}
	if (argc != 5 || !seconds || !out_path)
		fail("usage: kiosk-framepace --seconds N --out FILE");
	if (unlink(out_path) && errno != ENOENT)
		fail("remove %s: %s", out_path, strerror(errno));

	fd = open(CARD, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		fail("open %s: %s", CARD, strerror(errno));
	drmDropMaster(fd);
	crtc = find_crtc(fd, &pipe);
	crtc_id = crtc->crtc_id;
	w = crtc->mode.hdisplay;
	h = crtc->mode.vdisplay;
	vrefresh = crtc->mode.vrefresh;
	drmModeFreeCrtc(crtc);
	if (w != MODE_W || h != MODE_H) {
		fprintf(stderr, "kiosk-framepace: mode is %dx%d, not %dx%d\n", w, h, MODE_W, MODE_H);
		return 2;
	}

	out = fopen(out_path, "w");
	if (!out)
		fail("open %s: %s", out_path, strerror(errno));

	vblank = !wait_vblank(fd, pipe, &vbl);
	if (!vblank)
		snprintf(reason, sizeof(reason), " drmWaitVBlank: %s", strerror(errno));
	prev_seq = vbl.reply.sequence;

	utc(when, sizeof(when));
	fprintf(out, "H tool=%s\nH mode=%dx%d@%u\nH pacing=%s%s\nH regions=", FRAMEPACE_VERSION,
		w, h, vrefresh, vblank ? "vblank" : "timer100", reason);
	for (size_t s = 0; s < N_SPANS; s++)
		fprintf(out, "%s%u-%u", s ? "," : "x", SPAN_X[s][0], SPAN_X[s][1]);
	for (size_t r = 0; r < N_ROWS; r++)
		fprintf(out, "%s%u", r ? "," : ";y", ROW_Y[r]);
	fprintf(out, ";step%u\nH start=%s\nH seconds=%u\n", STEP, when, seconds);

	deadline = now_ns();
	t_end = deadline + (uint64_t)seconds * 1000000000u;
	while (now_ns() < t_end) {
		const struct fbmap *m;
		drmModeCrtcPtr c;
		uint32_t id;
		uint64_t hash;

		if (vblank) {
			if (wait_vblank(fd, pipe, &vbl))
				fail("drmWaitVBlank: %s", strerror(errno));
			if (vbl.reply.sequence - prev_seq > 1)
				missed += vbl.reply.sequence - prev_seq - 1;
			prev_seq = vbl.reply.sequence;
			snprintf(seq, sizeof(seq), "%u", vbl.reply.sequence);
		} else {
			struct timespec ts;

			deadline += TIMER_NS;
			t = now_ns();
			if (t >= deadline) {
				uint64_t k = (t - deadline) / TIMER_NS + 1;

				missed += k;
				deadline += k * TIMER_NS;
			}
			ts.tv_sec = deadline / 1000000000u;
			ts.tv_nsec = deadline % 1000000000u;
			while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL) == EINTR)
				;
		}

		c = drmModeGetCrtc(fd, crtc_id);
		if (!c)
			fail("drmModeGetCrtc(%u): %s", crtc_id, strerror(errno));
		id = c->buffer_id;
		drmModeFreeCrtc(c);
		if (!id)
			fail("CRTC %u has no framebuffer bound", crtc_id);
		m = map_fb(fd, id, crtc_id);

		t = now_ns();
		sync.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ;
		if (ioctl(m->pfd, DMA_BUF_IOCTL_SYNC, &sync))
			fail("DMA_BUF_IOCTL_SYNC start: %s", strerror(errno));
		hash = region_hash(m->map, m->off, m->n);
		sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
		if (ioctl(m->pfd, DMA_BUF_IOCTL_SYNC, &sync))
			fail("DMA_BUF_IOCTL_SYNC end: %s", strerror(errno));
		if (fprintf(out, "S %" PRIu64 " %u %016" PRIx64 " %s\n", t, id, hash, seq) < 0)
			fail("write %s: %s", out_path, strerror(errno));
		samples++;
	}

	getrusage(RUSAGE_SELF, &ru);
	utc(when, sizeof(when));
	fprintf(out, "H cpu_ms=%" PRIu64 "\nH samples=%" PRIu64 " missed=%" PRIu64 " end=%s\n",
		(uint64_t)(ru.ru_utime.tv_sec + ru.ru_stime.tv_sec) * 1000u +
			(uint64_t)(ru.ru_utime.tv_usec + ru.ru_stime.tv_usec) / 1000u,
		samples, missed, when);
	if (fclose(out))
		fail("close %s: %s", out_path, strerror(errno));
	return 0;
}
