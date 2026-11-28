/* kiosk-drmgrab: write the buffer the panel is scanning out to stdout.
 *
 * One line, `<width> <height> <pitch> <fourcc> <modifier>`, then the buffer's
 * bytes as they lie in memory; kiosk-screenshot.py, beside the recipe, decodes them. It is the
 * first lit CRTC's primary plane. Needs root, as DRM gives no one else a handle
 * to another client's buffer. Any failure exits 1 with the reason on stderr and
 * nothing on stdout.
 */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <linux/dma-buf.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

static void die(const char *what)
{
	fprintf(stderr, "kiosk-drmgrab: %s: %s\n", what, strerror(errno));
	exit(1);
}

static uint32_t scanned_out(int card)
{
	drmModeRes *resources = drmModeGetResources(card);

	if (!resources)
		die("no display resources");
	for (int i = 0; i < resources->count_crtcs; i++) {
		drmModeCrtc *crtc = drmModeGetCrtc(card, resources->crtcs[i]);

		if (crtc && crtc->mode_valid && crtc->buffer_id)
			return crtc->buffer_id;
	}
	fputs("kiosk-drmgrab: the panel is driven at no mode, or shows no buffer\n", stderr);
	exit(1);
}

int main(void)
{
	struct dma_buf_sync sync = { .flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ };
	int card = open("/dev/dri/card0", O_RDWR | O_CLOEXEC), buffer;
	drmModeFB2 *fb;
	off_t end;
	size_t size;
	void *map, *copy;

	if (card < 0)
		die("/dev/dri/card0");
	/* Opening the card with no master makes this one; the browser needs it. */
	drmDropMaster(card);

	fb = drmModeGetFB2(card, scanned_out(card));
	if (!fb)
		die("describe the buffer");
	if (!fb->handles[0]) {
		fputs("kiosk-drmgrab: the driver gives this user no handle to the buffer\n", stderr);
		exit(1);
	}
	if (drmPrimeHandleToFD(card, fb->handles[0], DRM_CLOEXEC, &buffer))
		die("export the buffer");
	end = lseek(buffer, 0, SEEK_END);
	if (end < 0)
		die("size the buffer");
	size = end - fb->offsets[0];
	map = mmap(NULL, fb->offsets[0] + size, PROT_READ, MAP_SHARED, buffer, 0);
	copy = malloc(size);
	if (map == MAP_FAILED || !copy)
		die("map the buffer");

	/* Copied first, so a slow reader does not hold the buffer. */
	if (ioctl(buffer, DMA_BUF_IOCTL_SYNC, &sync))
		die("wait for the buffer");
	memcpy(copy, (char *)map + fb->offsets[0], size);

	printf("%u %u %u %.4s %" PRIu64 "\n", fb->width, fb->height, fb->pitches[0],
	       (char *)&fb->pixel_format, fb->modifier);
	if (fwrite(copy, 1, size, stdout) != size || fflush(stdout))
		die("write the buffer");
	return 0;
}
