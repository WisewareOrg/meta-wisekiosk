/* Capture the firmware's composited output of display 0 as a binary PPM.
 *
 *   kiosk-fwgrab <out.ppm>
 *
 * Snapshots display 0 through DispmanX over vchiq (vc_dispmanx_snapshot into a
 * VC_IMAGE_RGB888 resource), so the frame is what the firmware composed for the
 * panel rather than one DRM plane. Needs /dev/vchiq.
 *
 * Output: P6, 8-bit RGB, the display's full size.
 *
 * Exit 0 on a written frame. Any failure exits 1 with the failed call on stderr
 * and leaves nothing at <out>: <out> is removed first, the frame is written to
 * <out>.tmp and renamed into place only once complete. The DispmanX resource and
 * display are released on every exit.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <bcm_host.h>

static const char *out_path;
static char *tmp_path;
static DISPMANX_DISPLAY_HANDLE_T display;
static DISPMANX_RESOURCE_HANDLE_T resource;

static void release(void)
{
	if (resource)
		vc_dispmanx_resource_delete(resource);
	if (display)
		vc_dispmanx_display_close(display);
	resource = 0;
	display = 0;
}

static void fail(const char *fmt, ...) __attribute__((format(printf, 1, 2), noreturn));

static void fail(const char *fmt, ...)
{
	va_list ap;

	fputs("kiosk-fwgrab: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
	if (tmp_path)
		unlink(tmp_path);
	release();
	exit(1);
}

int main(int argc, char **argv)
{
	DISPMANX_MODEINFO_T info;
	VC_RECT_T rect;
	uint32_t image_ptr, w, h, pitch;
	uint8_t *buf;
	FILE *out;

	if (argc != 2) {
		fputs("usage: kiosk-fwgrab <out.ppm>\n", stderr);
		return 1;
	}
	out_path = argv[1];
	if (unlink(out_path) && errno != ENOENT)
		fail("remove %s: %s", out_path, strerror(errno));

	bcm_host_init();
	display = vc_dispmanx_display_open(0);
	if (!display)
		fail("vc_dispmanx_display_open(0) failed");
	if (vc_dispmanx_display_get_info(display, &info))
		fail("vc_dispmanx_display_get_info failed");
	if (info.width <= 0 || info.height <= 0)
		fail("vc_dispmanx_display_get_info returned %dx%d", info.width, info.height);
	w = info.width;
	h = info.height;

	resource = vc_dispmanx_resource_create(VC_IMAGE_RGB888, w, h, &image_ptr);
	if (!resource)
		fail("vc_dispmanx_resource_create(RGB888, %ux%u) failed", w, h);
	if (vc_dispmanx_snapshot(display, resource, DISPMANX_NO_ROTATE))
		fail("vc_dispmanx_snapshot failed");

	pitch = ALIGN_UP(w * 3, 32);
	buf = malloc((size_t)pitch * h);
	if (!buf)
		fail("out of memory");
	vc_dispmanx_rect_set(&rect, 0, 0, w, h);
	if (vc_dispmanx_resource_read_data(resource, &rect, buf, pitch))
		fail("vc_dispmanx_resource_read_data failed");

	if (asprintf(&tmp_path, "%s.tmp", out_path) < 0) {
		tmp_path = NULL;
		fail("out of memory");
	}
	out = fopen(tmp_path, "wb");
	if (!out)
		fail("open %s: %s", tmp_path, strerror(errno));
	fprintf(out, "P6\n%u %u\n255\n", w, h);
	for (uint32_t y = 0; y < h; y++)
		if (fwrite(buf + (size_t)y * pitch, 3, w, out) != w)
			fail("write %s: %s", tmp_path, strerror(errno));
	if (fclose(out))
		fail("close %s: %s", tmp_path, strerror(errno));
	if (rename(tmp_path, out_path))
		fail("rename %s to %s: %s", tmp_path, out_path, strerror(errno));

	release();
	free(buf);
	return 0;
}
