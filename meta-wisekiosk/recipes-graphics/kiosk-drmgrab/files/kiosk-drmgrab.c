/* Capture the scanout of the active CRTC as a binary PPM.
 *
 *   kiosk-drmgrab <out.ppm> [WxH+X+Y]
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
 * Exit 0 on a written frame. Any failure exits 1 with the reason on stderr and
 * leaves nothing at <out>.
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
#include <unistd.h>

#include <linux/dma-buf.h>
#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#define CARD "/dev/dri/card0"

static const char *out_path;
static int out_created;

static void fail(const char *fmt, ...) __attribute__((format(printf, 1, 2), noreturn));

static void fail(const char *fmt, ...)
{
	va_list ap;

	fputs("kiosk-drmgrab: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
	if (out_created)
		unlink(out_path);
	exit(1);
}

/* Byte offset of pixel (x, y) in a 32 bpp VC4 T-tiled buffer. */
static size_t t_offset(uint32_t x, uint32_t y, uint32_t tiles_across)
{
	static const uint32_t even_stile[4] = {0, 3, 1, 2};
	static const uint32_t odd_stile[4] = {2, 1, 3, 0};
	uint32_t tile_x = x >> 5, tile_y = y >> 5;
	int odd = tile_y & 1;
	uint32_t stile = (((y >> 4) & 1) << 1) | ((x >> 4) & 1);
	uint32_t utile = (((y >> 2) & 3) << 2) | ((x >> 2) & 3);
	uint32_t pixel = ((y & 3) << 2) | (x & 3);

	if (odd)
		tile_x = tiles_across - tile_x - 1;
	return (size_t)4096 * (tile_y * tiles_across + tile_x) +
	       1024 * (odd ? odd_stile[stile] : even_stile[stile]) +
	       64 * utile + 4 * pixel;
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
	uint32_t cw, ch, cx, cy, tiles_across = 0;
	drmModeResPtr res;
	drmModeFB2Ptr fb = NULL;
	uint64_t modifier;
	size_t need, len;
	off_t end;
	uint8_t *map, *row;
	struct dma_buf_sync sync;
	FILE *out;
	int fd, pfd, i;

	if (argc < 2 || argc > 3) {
		fputs("usage: kiosk-drmgrab <out.ppm> [WxH+X+Y]\n", stderr);
		return 1;
	}
	out_path = argv[1];

	fd = open(CARD, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		fail("open %s: %s", CARD, strerror(errno));

	res = drmModeGetResources(fd);
	if (!res)
		fail("drmModeGetResources: %s", strerror(errno));
	for (i = 0; i < res->count_crtcs && !fb; i++) {
		drmModeCrtcPtr crtc = drmModeGetCrtc(fd, res->crtcs[i]);

		if (crtc && crtc->mode_valid && crtc->buffer_id) {
			fb = drmModeGetFB2(fd, crtc->buffer_id);
			if (!fb)
				fail("drmModeGetFB2(fb %u on crtc %u): %s", crtc->buffer_id,
				     crtc->crtc_id, strerror(errno));
		}
		drmModeFreeCrtc(crtc);
	}
	drmModeFreeResources(res);
	if (!fb)
		fail("no CRTC with a valid mode and a bound framebuffer");

	if (fb->pixel_format != DRM_FORMAT_XRGB8888 && fb->pixel_format != DRM_FORMAT_ARGB8888)
		fail("unsupported format %.4s (0x%08" PRIx32 ")", (const char *)&fb->pixel_format,
		     fb->pixel_format);
	if (!(fb->flags & DRM_MODE_FB_MODIFIERS))
		fail("framebuffer reports no modifier, so its layout is unknown");
	modifier = fb->modifier;
	if (modifier != DRM_FORMAT_MOD_LINEAR && modifier != DRM_FORMAT_MOD_BROADCOM_VC4_T_TILED)
		fail("unsupported modifier 0x%016" PRIx64 " (format %.4s)", modifier,
		     (const char *)&fb->pixel_format);
	if (!fb->handles[0])
		fail("GETFB2 returned no buffer handle (not root?)");

	cw = fb->width;
	ch = fb->height;
	cx = cy = 0;
	if (argc == 3) {
		parse_crop(argv[2], &cw, &ch, &cx, &cy);
		if ((uint64_t)cx + cw > fb->width || (uint64_t)cy + ch > fb->height)
			fail("crop %s lies outside the %ux%u framebuffer", argv[2], fb->width,
			     fb->height);
	}

	if (modifier == DRM_FORMAT_MOD_LINEAR) {
		if (fb->pitches[0] < fb->width * 4)
			fail("pitch %u is below width %u x 4", fb->pitches[0], fb->width);
		need = (size_t)fb->offsets[0] + (size_t)fb->pitches[0] * fb->height;
	} else {
		if (fb->pitches[0] % 128)
			fail("T-tiled pitch %u is not a whole number of 32-pixel tiles", fb->pitches[0]);
		tiles_across = fb->pitches[0] / 128;
		need = (size_t)fb->offsets[0] + (size_t)4096 * tiles_across * ((fb->height + 31) / 32);
	}

	if (drmPrimeHandleToFD(fd, fb->handles[0], DRM_CLOEXEC, &pfd))
		fail("drmPrimeHandleToFD: %s", strerror(errno));
	end = lseek(pfd, 0, SEEK_END);
	if (end < 0)
		fail("dma-buf size: %s", strerror(errno));
	len = (size_t)end;
	if (len < need)
		fail("dma-buf is %zu bytes, layout needs %zu", len, need);
	map = mmap(NULL, len, PROT_READ, MAP_SHARED, pfd, 0);
	if (map == MAP_FAILED)
		fail("mmap dma-buf: %s", strerror(errno));

	row = malloc((size_t)cw * 3);
	if (!row)
		fail("out of memory");

	out = fopen(out_path, "wb");
	if (!out)
		fail("open %s: %s", out_path, strerror(errno));
	out_created = 1;
	fprintf(out, "P6\n%u %u\n255\n", cw, ch);

	sync.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ;
	if (ioctl(pfd, DMA_BUF_IOCTL_SYNC, &sync))
		fail("DMA_BUF_IOCTL_SYNC start: %s", strerror(errno));
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
			fail("write %s: %s", out_path, strerror(errno));
	}
	sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
	if (ioctl(pfd, DMA_BUF_IOCTL_SYNC, &sync))
		fail("DMA_BUF_IOCTL_SYNC end: %s", strerror(errno));

	if (fclose(out))
		fail("close %s: %s", out_path, strerror(errno));

	munmap(map, len);
	close(pfd);
	drmCloseBufferHandle(fd, fb->handles[0]);
	drmModeFreeFB2(fb);
	close(fd);
	free(row);
	return 0;
}
