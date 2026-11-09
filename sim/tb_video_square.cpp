// Square mode. One 20×20 block follows the store at block (15, 11).
// Every other active pixel stays black, including while led is on.
// The arm input keeps the block dark until it is set.
#include "Vvideo.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>

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

static int in_square(int x, int y) {
  if (x < 144 || x >= 784 || y < 35 || y >= 515) return 0;
  int ax = x - 144;
  int ay = y - 35;
  return (ax / 20) == 15 && (ay / 20) == 11;
}

static void pulse(Vvideo* top, int bit) {
  top->screen_bit = bit;
  top->screen_we = 1;
  posedge(top);
  top->screen_we = 0;
  posedge(top);
  posedge(top);
}

static void frame(Vvideo* top, int want_square, const char* name) {
  int white = 0;
  int active = 0;
  int outside = 0;
  for (int i = 0; i < FRAME; i++) {
    posedge(top);
    int x = top->x_q;
    int y = top->y_q;
    int hs = x >= 96;
    int vs = y >= 2;
    int de = (x >= 144 && x < 784 && y >= 35 && y < 515);
    int sq = de && in_square(x, y);
    int on = sq && want_square;
    uint16_t want0 = de ? (on ? WHITE : BLACK) : ctrl(vs, hs);
    uint16_t want1 = de ? want0 : CTRL00;
    if ((int)top->de_q != de || (int)top->hs_q != hs || (int)top->vs_q != vs ||
        top->word0 != want0 || top->word1 != want1 || top->word2 != want1) {
      if (fails < 8) {
        fprintf(stderr,
                "FAIL %s i=%d x=%d y=%d de=%u hs=%u vs=%u w=%03x %03x %03x"
                " want de=%d w=%03x\n",
                name, i, x, y, top->de_q, top->hs_q, top->vs_q,
                top->word0, top->word1, top->word2, de, want0);
      }
      fails++;
    }
    if (de) active++;
    if (on && top->word0 == WHITE) white++;
    if (de && !sq && top->word0 != BLACK) outside++;
  }
  if (active != 640 * 480) {
    fprintf(stderr, "FAIL %s active %d\n", name, active);
    fails++;
  }
  int want_white = want_square ? 20 * 20 : 0;
  if (white != want_white || outside) {
    fprintf(stderr, "FAIL %s white %d want %d outside %d\n",
            name, white, want_white, outside);
    fails++;
  }
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  auto* top = new Vvideo;
  top->clk27 = 0;
  top->led = 1;
  top->pix_sim = 0;
  top->screen_we = 0;
  top->screen_bit = 0;
  top->armed = 0;
  top->eval();

  pulse(top, 1);
  frame(top, 0, "unarmed");

  top->armed = 1;
  pulse(top, 0);
  frame(top, 0, "cleared");

  pulse(top, 1);
  frame(top, 1, "set");

  top->led = 0;
  pulse(top, 0);
  frame(top, 0, "off");

  if (fails) {
    fprintf(stderr, "FAIL %d\n", fails);
    return 1;
  }
  printf("ok square 20x20 at block 15,11; outside stays black\n");
  return 0;
}
