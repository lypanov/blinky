// One frame of black, then one frame of white. Checks the fixed TMDS
// words and the 640×480 timing. No PLL, no serializer.
#include "Vvideo.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>

static const int H = 800;
static const int V = 525;
static const int FRAME = H * V;
static const uint16_t BLACK = 0b0111110000;
static const uint16_t WHITE = 0b1011110000;
static const uint16_t CTRL00 = 0b1101010100;
static const uint16_t CTRL01 = 0b0010101011;
static const uint16_t CTRL10 = 0b0101010100;
static const uint16_t CTRL11 = 0b1010101011;

static int fails = 0;

static void posedge(Vvideo* top) {
  top->pix_sim = 0;
  top->eval();
  top->pix_sim = 1;
  top->eval();
}

static uint16_t ctrl(int vs, int hs) {
  if (!vs && !hs) return CTRL00;
  if (!vs && hs) return CTRL01;
  if (vs && !hs) return CTRL10;
  return CTRL11;
}

static void check_pixel(Vvideo* top, int i, int white) {
  int x = i % H;
  int y = i / H;
  int hs = x >= 96;
  int vs = y >= 2;
  int de = (x >= 144 && x < 784 && y >= 35 && y < 515);
  uint16_t want0 = de ? (white ? WHITE : BLACK) : ctrl(vs, hs);
  uint16_t want1 = de ? want0 : CTRL00;
  if (top->x_q != x || top->y_q != y || (int)top->de_q != de ||
      (int)top->hs_q != hs || (int)top->vs_q != vs ||
      top->word0 != want0 || top->word1 != want1 || top->word2 != want1) {
    if (fails < 8) {
      fprintf(stderr,
              "FAIL i=%d got x=%u y=%u de=%u hs=%u vs=%u w=%03x %03x %03x"
              " want x=%d y=%d de=%d hs=%d vs=%d w=%03x %03x\n",
              i, top->x_q, top->y_q, top->de_q, top->hs_q, top->vs_q,
              top->word0, top->word1, top->word2, x, y, de, hs, vs, want0,
              want1);
    }
    fails++;
  }
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  auto* top = new Vvideo;
  top->clk27 = 0;
  top->led = 0;
  top->blank = 0;
  top->pix_sim = 0;
  top->eval();

  int active = 0;
  for (int i = 0; i < FRAME; i++) {
    posedge(top);
    check_pixel(top, i, 0);
    if (top->de_q) active++;
  }
  if (active != 640 * 480) {
    fprintf(stderr, "FAIL black frame active %d\n", active);
    fails++;
  }

  top->led = 1;
  active = 0;
  for (int i = 0; i < FRAME; i++) {
    posedge(top);
    // Two pixel clocks for the synchronizer. Both are blanking.
    check_pixel(top, i, i >= 2);
    if (top->de_q) active++;
  }
  if (active != 640 * 480) {
    fprintf(stderr, "FAIL white frame active %d\n", active);
    fails++;
  }

  // A press blanks the picture while led stays 1. Release shows white
  // again, the phase the LED input already has.
  top->blank = 1;
  active = 0;
  int white_px = 0;
  for (int i = 0; i < FRAME; i++) {
    posedge(top);
    check_pixel(top, i, 0);
    if (top->de_q) {
      active++;
      if (top->word0 == WHITE) white_px++;
    }
  }
  if (active != 640 * 480 || white_px != 0) {
    fprintf(stderr, "FAIL blanked frame active %d white %d\n", active, white_px);
    fails++;
  }
  top->blank = 0;
  active = 0;
  white_px = 0;
  for (int i = 0; i < FRAME; i++) {
    posedge(top);
    check_pixel(top, i, i >= 2);
    if (top->de_q) {
      active++;
      if (top->word0 == WHITE) white_px++;
    }
  }
  if (active != 640 * 480 || white_px != 640 * 480) {
    fprintf(stderr, "FAIL release frame active %d white %d\n", active, white_px);
    fails++;
  }

  // The arm gate is the LED input. Led low stays black on the next frame.
  top->led = 0;
  for (int i = 0; i < 4; i++) posedge(top);
  posedge(top);
  if (top->de_q) {
    fprintf(stderr, "FAIL expected blanking just after the vsync pulse\n");
    fails++;
  }

  if (fails) {
    fprintf(stderr, "FAIL %d mismatches\n", fails);
    return 1;
  }
  printf("ok 2 frames, 640x480, black then white\n");
  return 0;
}
