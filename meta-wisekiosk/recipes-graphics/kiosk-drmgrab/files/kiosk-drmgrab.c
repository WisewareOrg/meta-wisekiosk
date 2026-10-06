/* Capture the scanout of the active CRTC as a binary PPM.
 *
 *   kiosk-drmgrab [--report] <out.ppm> [WxH+X+Y]
 *
 * Reads the framebuffer bound to the first CRTC on /dev/dri/card0 that has a
 * valid mode and a non-zero buffer_id (its primary plane), via DRM GETFB2. The
 * buffer is exported as a dma-buf (prime fd) and mmap'd read-only, bracketed by
 * DMA_BUF_IOCTL_SYNC, so dumb buffers and vc4/GBM BOs map the same way. Needs
 * root: GETFB2 returns no handle to an unprivileged non-master client.
 *
 * Supported: formats XR24/AR24, modifiers LINEAR and BROADCOM_VC4_T_TILED. The
 * T-tiled layout is mesa's (src/gallium/drivers/vc4/vc4_tiling.c): 4x4-pixel
 * 64 B utiles, 1 KB subtiles of 4x4 utiles in raster order, 4 KB tiles of 2x2
 * subtiles, tile rows alternating left-to-right and right-to-left.
 *
 * Output: P6, 8-bit RGB, the X/alpha channel dropped; optionally cropped to
 * WxH+X+Y, which must lie inside the framebuffer.
 *
 * --report: on success, one line on stderr, "fb_before=<id> fb_after=<id>
 * copy_ms=<int>": the buffer_id read, the same CRTC's buffer_id re-read after
 * the copy (0 if that read fails), and the whole milliseconds from the start of
 * the pixel read to the end of DMA_BUF_IOCTL_SYNC.
 *
 * Drops DRM master straight after opening the card, leaving master free for a
 * display server that starts during a capture.
 *
 * Exit 0 on a written frame. Any failure exits 1 with the reason on stderr and
 * leaves nothing at <out>: <out> is removed first, the frame is written to
 * <out>.tmp and renamed into place only once complete.
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
#include <time.h>
#include <unistd.h>

#include <linux/dma-buf.h>
#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#define CARD "/dev/dri/card0"

static const char *out_path;
static char *tmp_path;

static void fail(const char *fmt, ...) __attribute__((format(printf, 1, 2), noreturn));

static void fail(const char *fmt, ...)
{
	va_list ap;

	fputs("kiosk-drmgrab: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
	if (tmp_path)
		unlink(tmp_path);
	exit(1);
}

#include "kiosk-scanout.h"

static uint64_t now_ns(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
}

static void parse_crop(const char *s, uint32_t *w, uint32_t *h, uint32_t *x, uint32_t *y)
{
	char tail;

	if (sscanf(s, "%" SCNu32 "x%" SCNu32 "+%" SCNu32 "+%" SCNu32 "%c", w, h, x, y, &tail) != 4 ||
	    *w == 0 || *h == 0)
		fail("bad crop geometry '%s' -- expected WxH+X+Y", s);
}

int main(int argc, char **argv)
{
	uint32_t cw, ch, cx, cy, tiles_across, crtc_id, fb_before, fb_after = 0, pipe;
	uint64_t t0, t1;
	drmModeCrtcPtr crtc, after;
	int report = 0;
	drmModeFB2Ptr fb;
	uint64_t modifier;
	size_t len;
	const uint8_t *map;
	uint8_t *row;
	struct dma_buf_sync sync;
	FILE *out;
	int fd, pfd;

	if (argc > 1 && !strcmp(argv[1], "--report")) {
		report = 1;
		argv++;
		argc--;
	}
	if (argc < 2 || argc > 3) {
		fputs("usage: kiosk-drmgrab [--report] <out.ppm> [WxH+X+Y]\n", stderr);
		return 1;
	}
	out_path = argv[1];
	if (unlink(out_path) && errno != ENOENT)
		fail("remove %s: %s", out_path, strerror(errno));

	fd = open(CARD, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		fail("open %s: %s", CARD, strerror(errno));
	drmDropMaster(fd);

	crtc = find_crtc(fd, &pipe);
	crtc_id = crtc->crtc_id;
	fb_before = crtc->buffer_id;
	drmModeFreeCrtc(crtc);
	fb = fb_get(fd, fb_before, crtc_id);
	modifier = fb->modifier;

	cw = fb->width;
	ch = fb->height;
	cx = cy = 0;
	if (argc == 3) {
		parse_crop(argv[2], &cw, &ch, &cx, &cy);
		if ((uint64_t)cx + cw > fb->width || (uint64_t)cy + ch > fb->height)
			fail("crop %s lies outside the %ux%u framebuffer", argv[2], fb->width,
			     fb->height);
	}

	map = fb_map(fd, fb, &pfd, &len);
	tiles_across = fb->pitches[0] / 128;

	row = malloc((size_t)cw * 3);
	if (!row)
		fail("out of memory");

	if (asprintf(&tmp_path, "%s.tmp", out_path) < 0) {
		tmp_path = NULL;
		fail("out of memory");
	}
	out = fopen(tmp_path, "wb");
	if (!out)
		fail("open %s: %s", tmp_path, strerror(errno));
	fprintf(out, "P6\n%u %u\n255\n", cw, ch);

	sync.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ;
	if (ioctl(pfd, DMA_BUF_IOCTL_SYNC, &sync))
		fail("DMA_BUF_IOCTL_SYNC start: %s", strerror(errno));
	t0 = now_ns();
	for (uint32_t y = cy; y < cy + ch; y++) {
		for (uint32_t x = cx; x < cx + cw; x++) {
			const uint8_t *p = map + fb->offsets[0] +
					   (modifier == DRM_FORMAT_MOD_LINEAR
						    ? (size_t)y * fb->pitches[0] + (size_t)x * 4
						    : t_offset(x, y, tiles_across));
			uint8_t *q = row + (size_t)(x - cx) * 3;
			uint32_t v;

			/* One 32-bit load per pixel: the mapping is uncached. */
			memcpy(&v, p, 4);
			q[0] = v >> 16;
			q[1] = v >> 8;
			q[2] = v;
		}
		if (fwrite(row, 3, cw, out) != cw)
			fail("write %s: %s", tmp_path, strerror(errno));
	}
	sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
	if (ioctl(pfd, DMA_BUF_IOCTL_SYNC, &sync))
		fail("DMA_BUF_IOCTL_SYNC end: %s", strerror(errno));
	t1 = now_ns();
	if (report) {
		after = drmModeGetCrtc(fd, crtc_id);
		if (after)
			fb_after = after->buffer_id;
		drmModeFreeCrtc(after);
	}

	if (fclose(out))
		fail("close %s: %s", tmp_path, strerror(errno));
	if (rename(tmp_path, out_path))
		fail("rename %s to %s: %s", tmp_path, out_path, strerror(errno));

	munmap((void *)map, len);
	close(pfd);
	drmCloseBufferHandle(fd, fb->handles[0]);
	drmModeFreeFB2(fb);
	close(fd);
	free(row);
	if (report)
		fprintf(stderr, "fb_before=%u fb_after=%u copy_ms=%" PRIu64 "\n", fb_before, fb_after,
			(t1 - t0) / 1000000u);
	return 0;
}
