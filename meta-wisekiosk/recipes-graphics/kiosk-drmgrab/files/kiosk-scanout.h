/* Scanout access shared by kiosk-drmgrab.c and kiosk-framepace.c: the active
 * CRTC, its framebuffer's lookup and read-only dma-buf mapping, and the VC4
 * T-tiled address map. The including file supplies the headers and defines
 * fail() before including this one.
 */

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

/* The first CRTC with a valid mode and a bound framebuffer; *pipe is its index. */
static drmModeCrtcPtr find_crtc(int fd, uint32_t *pipe)
{
	drmModeCrtcPtr found = NULL;
	drmModeResPtr res;
	int i;

	res = drmModeGetResources(fd);
	if (!res)
		fail("drmModeGetResources: %s", strerror(errno));
	for (i = 0; i < res->count_crtcs && !found; i++) {
		drmModeCrtcPtr crtc = drmModeGetCrtc(fd, res->crtcs[i]);

		if (crtc && crtc->mode_valid && crtc->buffer_id) {
			found = crtc;
			*pipe = i;
		} else {
			drmModeFreeCrtc(crtc);
		}
	}
	drmModeFreeResources(res);
	if (!found)
		fail("no CRTC with a valid mode and a bound framebuffer");
	return found;
}

/* GETFB2 on fb_id, refused unless XR24/AR24, LINEAR or VC4 T-tiled, with a handle. */
static drmModeFB2Ptr fb_get(int fd, uint32_t fb_id, uint32_t crtc_id)
{
	drmModeFB2Ptr fb = drmModeGetFB2(fd, fb_id);

	if (!fb)
		fail("drmModeGetFB2(fb %u on crtc %u): %s", fb_id, crtc_id, strerror(errno));
	if (fb->pixel_format != DRM_FORMAT_XRGB8888 && fb->pixel_format != DRM_FORMAT_ARGB8888)
		fail("unsupported format %.4s (0x%08" PRIx32 ")", (const char *)&fb->pixel_format,
		     fb->pixel_format);
	if (!(fb->flags & DRM_MODE_FB_MODIFIERS))
		fail("framebuffer reports no modifier, so its layout is unknown");
	if (fb->modifier != DRM_FORMAT_MOD_LINEAR &&
	    fb->modifier != DRM_FORMAT_MOD_BROADCOM_VC4_T_TILED)
		fail("unsupported modifier 0x%016" PRIx64 " (format %.4s)", (uint64_t)fb->modifier,
		     (const char *)&fb->pixel_format);
	if (!fb->handles[0])
		fail("GETFB2 returned no buffer handle (not root?)");
	return fb;
}

/* Prime-export fb and mmap it read-only, after checking its pitch and size. */
static const uint8_t *fb_map(int fd, const drmModeFB2 *fb, int *pfd, size_t *len)
{
	size_t need;
	off_t end;
	void *map;

	if (fb->modifier == DRM_FORMAT_MOD_LINEAR) {
		if (fb->pitches[0] < fb->width * 4)
			fail("pitch %u is below width %u x 4", fb->pitches[0], fb->width);
		need = (size_t)fb->offsets[0] + (size_t)fb->pitches[0] * fb->height;
	} else {
		if (fb->pitches[0] % 128)
			fail("T-tiled pitch %u is not a whole number of 32-pixel tiles", fb->pitches[0]);
		need = (size_t)fb->offsets[0] +
		       (size_t)4096 * (fb->pitches[0] / 128) * ((fb->height + 31) / 32);
	}

	if (drmPrimeHandleToFD(fd, fb->handles[0], DRM_CLOEXEC, pfd))
		fail("drmPrimeHandleToFD: %s", strerror(errno));
	end = lseek(*pfd, 0, SEEK_END);
	if (end < 0)
		fail("dma-buf size: %s", strerror(errno));
	*len = (size_t)end;
	if (*len < need)
		fail("dma-buf is %zu bytes, layout needs %zu", *len, need);
	map = mmap(NULL, *len, PROT_READ, MAP_SHARED, *pfd, 0);
	if (map == MAP_FAILED)
		fail("mmap dma-buf: %s", strerror(errno));
	return map;
}
