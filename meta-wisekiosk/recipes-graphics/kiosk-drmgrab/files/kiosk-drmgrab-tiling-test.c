/* Host test for kiosk-drmgrab.c's t_offset(): the VC4 T-tiled address map.
 *
 *   ./kiosk-drmgrab-tiling-test.sh
 *
 * Pins the SHIPPED t_offset() -- extracted verbatim by the .sh driver into
 * shipped_t_offset.inc, never a copy of this file's own code -- against an
 * INDEPENDENT transcription below, ref_t_offset(), derived by hand straight
 * from mesa 24.0.7's VC4 tiling source (build/downloads/mesa-24.0.7.tar.xz),
 * not from kiosk-drmgrab.c:
 *
 *   src/gallium/drivers/vc4/vc4_tiling.c:70-114  t_utile_address(): the 4k
 *     tile's 4096 B stride, the odd-tile-row x-flip, and the subtile index
 *     map (even_stile_map / odd_stile_map).
 *   src/gallium/drivers/vc4/vc4_tiling_lt.c:130-159  vc4_lt_image_aligned(),
 *     hand-traced for cpp=4 (utile_w=utile_h=4, gpu_lt_stride=64): its
 *     gpu_tile address reduces to 64*(4*utile_y_local + utile_x_local), a
 *     row-major 4x4 grid of 64 B utiles within the 1 KB subtile.
 *   src/broadcom/common/v3d_cpu_tiling.h  v3d_load_utile()'s portable
 *     (non-NEON) fallback: 4 rows of 16 B (gpu_stride) copied in sequence,
 *     i.e. a row-major 4x4 grid of 4 B pixels within the 64 B utile.
 *
 * Bench's X scanout is 1280x720, pitch 5120 B (tiles_across = 5120/128 = 40),
 * spanning 920 4k tiles = 3768320 B (kiosk-drmgrab.c's commit message).
 * Checked: every pixel of that buffer against ref_t_offset; seven
 * hand-computed cases (walked out by hand, independent of both
 * implementations) against both; and that the map is a bijection onto
 * distinct byte offsets, every one inside the span.
 *
 * TO WATCH THIS FAIL -- seed a one-line defect in a SCRATCH COPY of
 * kiosk-drmgrab.c (never the tracked file) and point the .sh driver's
 * extraction at that copy instead. Swapping even_stile/odd_stile's two array
 * literals, or flipping the tile_y odd test to test tile_x instead, each
 * takes the full-buffer cross-check and the bijection check red. Discard the
 * scratch copy afterwards.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

#include "shipped_t_offset.inc"  /* static size_t t_offset(uint32_t, uint32_t, uint32_t); */

/* Independent transcription -- every term named for its mesa source, not
 * copied from t_offset() above. */
static size_t ref_t_offset(uint32_t x, uint32_t y, uint32_t tiles_across)
{
	uint32_t tile_x = x / 32, tile_y = y / 32;            /* vc4_tiling.c:80-81 */
	int odd_tile_row = tile_y % 2;                        /* :82 */
	if (odd_tile_row)                                     /* :85-86 */
		tile_x = tiles_across - tile_x - 1;
	size_t tile_offset = 4096 * ((size_t)tile_y * tiles_across + tile_x); /* :88 */

	uint32_t stile_x = (x / 16) % 2, stile_y = (y / 16) % 2; /* :90-91 */
	uint32_t stile_index = stile_y * 2 + stile_x;            /* :92 */
	static const uint32_t even_map[4] = {0, 3, 1, 2};        /* :94 */
	static const uint32_t odd_map[4]  = {2, 1, 3, 0};        /* :93 */
	size_t stile_offset = 1024 * (odd_tile_row ? odd_map[stile_index]
						    : even_map[stile_index]); /* :96-98 */

	/* vc4_tiling_lt.c:130-159, hand-traced for cpp=4: row-major 4x4 utile grid */
	uint32_t utile_x = (x / 4) % 4, utile_y = (y / 4) % 4;
	size_t utile_offset = 64 * ((size_t)utile_y * 4 + utile_x);

	/* v3d_cpu_tiling.h's non-NEON v3d_load_utile fallback: row-major 4x4 pixel grid */
	uint32_t px = x % 4, py = y % 4;
	size_t pixel_offset = 4 * ((size_t)py * 4 + px);

	return tile_offset + stile_offset + utile_offset + pixel_offset;
}

static int fails = 0;

static void check(const char *name, int cond)
{
	printf("[%s] %s\n", cond ? "PASS" : "FAIL", name);
	if (!cond)
		fails++;
}

/* Hand-computed, independent of BOTH implementations above. */
struct case_ { uint32_t x, y; size_t want; };
static const struct case_ HAND[] = {
	{0, 0, 0},            /* first pixel of the buffer */
	{3, 0, 12},           /* last pixel of utile 0's first row */
	{4, 0, 64},           /* first pixel of the second utile, same subtile */
	{16, 0, 3072},        /* first pixel of the second subtile (even tile row) */
	{32, 0, 4096},        /* first pixel of the second 4k tile, same tile row */
	{0, 32, 325632},      /* first pixel of the second tile row -- x-flip applies */
	{1279, 719, 3768316}, /* last pixel of the buffer -- 4 B short of the span */
};

int main(void)
{
	const uint32_t W = 1280, H = 720, TILES_ACROSS = 40;
	const size_t SPAN = 3768320;

	for (size_t i = 0; i < sizeof(HAND) / sizeof(HAND[0]); i++) {
		size_t got_shipped = t_offset(HAND[i].x, HAND[i].y, TILES_ACROSS);
		size_t got_ref = ref_t_offset(HAND[i].x, HAND[i].y, TILES_ACROSS);
		char name[80];
		snprintf(name, sizeof(name), "hand case (%u,%u): shipped t_offset == %zu",
			 HAND[i].x, HAND[i].y, HAND[i].want);
		check(name, got_shipped == HAND[i].want);
		snprintf(name, sizeof(name), "hand case (%u,%u): ref_t_offset == %zu",
			 HAND[i].x, HAND[i].y, HAND[i].want);
		check(name, got_ref == HAND[i].want);
	}

	/* Full-buffer cross-check + bijection. A bitmap of SPAN bytes is cheap at
	 * this size (3.77 MB) and makes a collision check a single array read. */
	unsigned char *seen = calloc(SPAN, 1);
	if (!seen) {
		fprintf(stderr, "out of memory allocating the %zu B bitmap\n", SPAN);
		return 1;
	}
	int mismatch = 0, out_of_range = 0, collision = 0;
	size_t max_off = 0;
	for (uint32_t y = 0; y < H; y++) {
		for (uint32_t x = 0; x < W; x++) {
			size_t a = t_offset(x, y, TILES_ACROSS);
			size_t b = ref_t_offset(x, y, TILES_ACROSS);
			if (a != b)
				mismatch++;
			if (a >= SPAN) {
				out_of_range++;
				continue;
			}
			if (seen[a])
				collision++;
			seen[a] = 1;
			if (a > max_off)
				max_off = a;
		}
	}
	free(seen);
	check("every pixel of 1280x720: shipped t_offset == ref_t_offset", mismatch == 0);
	check("every offset lies inside the 3768320 B span", out_of_range == 0);
	check("the map is a bijection (no two pixels share an offset)", collision == 0);
	check("max offset + 4 == span (the last pixel ends exactly at the span)",
	      max_off + 4 == SPAN);

	if (fails) {
		fprintf(stderr, "\n%d check(s) FAILED\n", fails);
		return 1;
	}
	printf("\nall checks passed\n");
	return 0;
}
