/* Host test for kiosk-scanout.h's t_offset(), the VC4 T-tiled address map, and
 * kiosk-framepace.c's region_offsets() and region_hash().
 *
 *   ./kiosk-drmgrab-tiling-test.sh
 *
 * Pins the SHIPPED t_offset() -- extracted verbatim by the .sh driver into
 * shipped_t_offset.inc, never a copy of this file's own code -- against an
 * INDEPENDENT transcription below, ref_t_offset(), derived by hand straight
 * from mesa 24.0.7's VC4 tiling source (build/downloads/mesa-24.0.7.tar.xz),
 * not from kiosk-scanout.h:
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
 * kiosk-framepace's region block (shipped_region.inc) is checked against
 * ref_region_hash(), the record format's hash restated here: FNV-1a 64 over
 * R,G,B of every pixel of x 70-325 then 434-688 (inclusive) on each of the 10
 * marquee scanlines, y ascending. The synthetic buffers are filled through
 * ref_t_offset (T-tiled) and a plain pitch (linear); the X byte varies per
 * pixel and must not reach the hash; a changed pixel at each span end changes
 * the hash, and one just outside the region does not.
 *
 * TO WATCH THIS FAIL -- seed a one-line defect in a SCRATCH COPY of
 * kiosk-scanout.h (never the tracked file) and point the .sh driver's
 * extraction at that copy instead. Swapping even_stile/odd_stile's two array
 * literals, or flipping the tile_y odd test to test tile_x instead, each
 * takes the full-buffer cross-check and the bijection check red. Discard the
 * scratch copy afterwards.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "shipped_t_offset.inc"  /* static size_t t_offset(uint32_t, uint32_t, uint32_t); */
#include "shipped_region.inc"    /* region_offsets(), region_hash() */

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

/* Region pixels: R,G,B from (x, y); the X byte is separate so it can vary. */
static uint32_t pix(uint32_t x, uint32_t y, uint32_t xbyte)
{
	return (xbyte << 24) | ((x * 2654435761u ^ y * 40503u) & 0xffffff);
}

static const uint32_t REF_Y[10] = {303, 326, 350, 388, 411, 522, 545, 568, 607, 630};
static const uint32_t REF_X[2][2] = {{70, 325}, {434, 688}};

static uint64_t ref_region_hash(void)
{
	uint64_t h = 0xcbf29ce484222325u;

	for (int r = 0; r < 10; r++)
		for (int s = 0; s < 2; s++)
			for (uint32_t x = REF_X[s][0]; x <= REF_X[s][1]; x++) {
				uint32_t v = pix(x, REF_Y[r], 0);
				uint8_t b[3] = {v >> 16, v >> 8, v};

				for (int i = 0; i < 3; i++)
					h = (h ^ b[i]) * 0x100000001b3u;
			}
	return h;
}

/* Fill a 1280x720 buffer; tiled selects ref_t_offset, else a 5120 B pitch. */
static void fill(uint8_t *buf, int tiled, uint32_t xbyte_salt)
{
	for (uint32_t y = 0; y < 720; y++)
		for (uint32_t x = 0; x < 1280; x++) {
			uint32_t v = pix(x, y, (x + y + xbyte_salt) & 0xff);

			memcpy(buf + (tiled ? ref_t_offset(x, y, 40) : (size_t)y * 5120 + x * 4), &v, 4);
		}
}

static void region_checks(int tiled)
{
	const char *kind = tiled ? "T-tiled" : "linear";
	uint8_t *buf = calloc(3768320, 1);
	size_t *off = malloc(sizeof(*off) * 10 * 1280);
	uint64_t want = ref_region_hash(), base;
	char name[96];
	size_t n;

	if (!buf || !off) {
		fprintf(stderr, "out of memory allocating the region buffers\n");
		exit(1);
	}
	fill(buf, tiled, 0);
	n = region_offsets(off, tiled, 5120, 0);
	snprintf(name, sizeof(name), "%s: region_offsets covers 5110 pixels", kind);
	check(name, n == 5110);
	base = region_hash(buf, off, n);
	snprintf(name, sizeof(name), "%s: region_hash == ref_region_hash", kind);
	check(name, base == want);

	fill(buf, tiled, 77);
	snprintf(name, sizeof(name), "%s: a different X byte leaves the hash unchanged", kind);
	check(name, region_hash(buf, off, n) == base);

	static const struct { uint32_t x, y; int in; } POKE[] = {
		{70, 303, 1}, {325, 303, 1}, {434, 630, 1}, {688, 630, 1},
		{69, 303, 0}, {326, 303, 0}, {433, 630, 0}, {689, 630, 0}, {200, 302, 0},
	};
	for (size_t i = 0; i < sizeof(POKE) / sizeof(POKE[0]); i++) {
		size_t at = tiled ? ref_t_offset(POKE[i].x, POKE[i].y, 40)
				  : (size_t)POKE[i].y * 5120 + POKE[i].x * 4;

		buf[at] ^= 0x01;
		snprintf(name, sizeof(name), "%s: a changed pixel at (%u,%u) %s the hash", kind,
			 POKE[i].x, POKE[i].y, POKE[i].in ? "changes" : "leaves");
		check(name, (region_hash(buf, off, n) != base) == POKE[i].in);
		buf[at] ^= 0x01;
	}
	free(off);
	free(buf);
}

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

	region_checks(1);
	region_checks(0);

	if (fails) {
		fprintf(stderr, "\n%d check(s) FAILED\n", fails);
		return 1;
	}
	printf("\nall checks passed\n");
	return 0;
}
