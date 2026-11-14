// Square mode. One 20×20 block follows the store at block (15, 11).
// Every other active pixel stays black, including while led is on.
// The arm input keeps the block dark until it is set.
#include "Vvideo.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>

static const int H = 858;
static const int V = 525;
static const int AW = 720;
static const int AH = 480;
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
  if (x < 122 || x >= 842 || y < 36 || y >= 516) return 0;
  int ax = x - 122;
  int ay = y - 36;
  return (ax / 20) == 15 && (ay / 20) == 11;
}

static void status_pulse(Vvideo* top, int word) {
  top->status_in = word;
  top->status_we = 1;
  posedge(top);
  top->status_we = 0;
  posedge(top);
  posedge(top);
}

static void pulse(Vvideo* top, int bit) {
  // Five rows of the 4K bitmap. Bits 11..15, word 442, stride 8.
  uint32_t data = bit ? 0x0000F800u : 0;
  for (int i = 0; i < 5; i++) {
    top->bmp_word = 442 + i * 8;
    top->bmp_data = data;
    top->screen_we = 1;
    posedge(top);
    top->screen_we = 0;
  }
  posedge(top);
  posedge(top);
}

static void to_frame(Vvideo* top) {
  for (int i = 0; i < 4; i++) posedge(top);
  for (int i = 0; i < FRAME + 8; i++) {
    if (top->x_q == 0 && top->y_q == 0) return;
    posedge(top);
  }
  fprintf(stderr, "FAIL no frame start\n");
  fails++;
}

static int marker_row(int y) {
  return y >= 36 && y < 38;
}

static void frame(Vvideo* top, int want_square, const char* name) {
  int white = 0;
  int active = 0;
  int outside = 0;
  int green = 0;
  for (int i = 0; i < FRAME; i++) {
    posedge(top);
    int x = top->x_q;
    int y = top->y_q;
    int hs = x >= 62;
    int vs = y >= 6;
    int de = (x >= 122 && x < 842 && y >= 36 && y < 516);
    int sq = de && in_square(x, y);
    int on = sq && want_square;
    int mark = de && marker_row(y);
    uint16_t want0 = de ? ((on && !mark) ? WHITE : BLACK) : ctrl(vs, hs);
    uint16_t want1 = de ? ((on || mark) ? WHITE : BLACK) : CTRL00;
    uint16_t want2 = de ? ((on && !mark) ? WHITE : BLACK) : CTRL00;
    if ((int)top->de_q != de || (int)top->hs_q != hs || (int)top->vs_q != vs ||
        top->word0 != want0 || top->word1 != want1 || top->word2 != want2) {
      if (fails < 8) {
        fprintf(stderr,
                "FAIL %s i=%d x=%d y=%d de=%u hs=%u vs=%u w=%03x %03x %03x"
                " want de=%d w=%03x %03x %03x\n",
                name, i, x, y, top->de_q, top->hs_q, top->vs_q,
                top->word0, top->word1, top->word2, de, want0, want1, want2);
      }
      fails++;
    }
    if (de) active++;
    if (on && top->word0 == WHITE) white++;
    if (mark && top->word0 == BLACK && top->word1 == WHITE && top->word2 == BLACK)
      green++;
    if (de && !sq && !mark && top->word0 != BLACK) outside++;
  }
  if (active != AW * AH) {
    fprintf(stderr, "FAIL %s active %d\n", name, active);
    fails++;
  }
  int want_white = want_square ? 20 * 20 : 0;
  int want_green = AW * 2;
  if (white != want_white || outside || green != want_green) {
    fprintf(stderr, "FAIL %s white %d want %d outside %d green %d want %d\n",
            name, white, want_white, outside, green, want_green);
    fails++;
  }
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  auto* top = new Vvideo;
  top->clk27 = 0;
  top->led = 1;
  top->blank = 0;
  top->pix_sim = 0;
  top->screen_we = 0;
  top->screen_bit = 0;
  top->bmp_data = 0;
  top->bmp_word = 0;
  top->armed = 0;
  top->status_we = 0;
  top->status_in = 0;
  top->eval();

  // Bit 8 selects today's square. Until it is set the picture is the
  // status blocks, and a zero register is all dark.
  status_pulse(top, 0x100);
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

  // The bit stays set. Blanking hides it, and release shows it again.
  pulse(top, 1);
  top->blank = 1;
  to_frame(top);
  frame(top, 0, "blanked");
  top->blank = 0;
  to_frame(top);
  frame(top, 1, "released");

  if (fails) {
    fprintf(stderr, "FAIL %d\n", fails);
    return 1;
  }
  printf("ok square 20x20 at block 15,11; outside stays black\n");
  return 0;
}
