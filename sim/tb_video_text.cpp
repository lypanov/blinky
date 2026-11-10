// Text mode. The 40x15 window is drawn from stores, with the same
// 8x8 font the host uses. The square is still block (15, 11). Both
// stay black until armed. led does not paint the field.
#include "Vvideo.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstring>

static const int H = 800;
static const int V = 525;
static const int FRAME = H * V;
static const int TEXT_X = 160;
static const int TEXT_Y = 48;
static const int DIGIT_COL0 = 18;
static const uint16_t BLACK = 0b0111110000;
static const uint16_t WHITE = 0b1011110000;
static const uint16_t CTRL00 = 0b1101010100;
static const uint16_t CTRL01 = 0b0010101011;
static const uint16_t CTRL10 = 0b0101010100;
static const uint16_t CTRL11 = 0b1010101011;

static int fails = 0;
static uint8_t font[128][8];
static uint8_t cells[15][40];

static void load_font() {
  std::memset(font, 0, sizeof font);
  // FONT8 BEGIN
  font[48][0] = 0x7E;
  font[48][1] = 0x81;
  font[48][2] = 0x81;
  font[48][3] = 0x81;
  font[48][4] = 0x81;
  font[48][5] = 0x81;
  font[48][6] = 0x7E;
  font[48][7] = 0x00;
  font[49][0] = 0x18;
  font[49][1] = 0x38;
  font[49][2] = 0x18;
  font[49][3] = 0x18;
  font[49][4] = 0x18;
  font[49][5] = 0x18;
  font[49][6] = 0x7E;
  font[49][7] = 0x00;
  font[50][0] = 0x7E;
  font[50][1] = 0x02;
  font[50][2] = 0x02;
  font[50][3] = 0x7E;
  font[50][4] = 0x80;
  font[50][5] = 0x80;
  font[50][6] = 0x7E;
  font[50][7] = 0x00;
  font[51][0] = 0x7E;
  font[51][1] = 0x02;
  font[51][2] = 0x02;
  font[51][3] = 0x7E;
  font[51][4] = 0x02;
  font[51][5] = 0x02;
  font[51][6] = 0x7E;
  font[51][7] = 0x00;
  font[52][0] = 0x81;
  font[52][1] = 0x81;
  font[52][2] = 0x81;
  font[52][3] = 0x7E;
  font[52][4] = 0x02;
  font[52][5] = 0x02;
  font[52][6] = 0x02;
  font[52][7] = 0x00;
  font[53][0] = 0x7E;
  font[53][1] = 0x80;
  font[53][2] = 0x80;
  font[53][3] = 0x7E;
  font[53][4] = 0x02;
  font[53][5] = 0x02;
  font[53][6] = 0x7E;
  font[53][7] = 0x00;
  font[54][0] = 0x7E;
  font[54][1] = 0x80;
  font[54][2] = 0x80;
  font[54][3] = 0x7E;
  font[54][4] = 0x81;
  font[54][5] = 0x81;
  font[54][6] = 0x7E;
  font[54][7] = 0x00;
  font[55][0] = 0x7E;
  font[55][1] = 0x02;
  font[55][2] = 0x02;
  font[55][3] = 0x04;
  font[55][4] = 0x08;
  font[55][5] = 0x10;
  font[55][6] = 0x10;
  font[55][7] = 0x00;
  font[56][0] = 0x7E;
  font[56][1] = 0x81;
  font[56][2] = 0x81;
  font[56][3] = 0x7E;
  font[56][4] = 0x81;
  font[56][5] = 0x81;
  font[56][6] = 0x7E;
  font[56][7] = 0x00;
  font[57][0] = 0x7E;
  font[57][1] = 0x81;
  font[57][2] = 0x81;
  font[57][3] = 0x7E;
  font[57][4] = 0x02;
  font[57][5] = 0x02;
  font[57][6] = 0x7E;
  font[57][7] = 0x00;
  // FONT8 END
}

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

static int glyph_on(int x, int y) {
  if (x < 144 || x >= 784 || y < 35 || y >= 515) return 0;
  int ax = x - 144;
  int ay = y - 35;
  if (ax < TEXT_X || ax >= TEXT_X + 320 || ay < TEXT_Y || ay >= TEXT_Y + 120)
    return 0;
  int col = (ax - TEXT_X) / 8;
  int row = (ay - TEXT_Y) / 8;
  int subx = (ax - TEXT_X) % 8;
  int suby = (ay - TEXT_Y) % 8;
  int ch = cells[row][col];
  return (font[ch][suby] >> (7 - subx)) & 1;
}

static int square_on(int x, int y, int square) {
  if (!square) return 0;
  if (x < 144 || x >= 784 || y < 35 || y >= 515) return 0;
  int ax = x - 144;
  int ay = y - 35;
  return ax >= 300 && ax < 320 && ay >= 220 && ay < 240;
}

static void put_count(Vvideo* top, int count) {
  int shown = count % 10000;
  if (count >= 10000 && count < 20000) shown = count - 10000;
  char buf[8];
  std::snprintf(buf, sizeof buf, "%04d", shown);
  std::memset(cells, 0, sizeof cells);
  for (int i = 0; i < 4; i++)
    cells[0][DIGIT_COL0 + i] = (uint8_t)buf[i];
  top->text_word = count;
  top->text_we = 1;
  posedge(top);
  top->text_we = 0;
  // The store latches the count. Fourteen clocks a digit, four digits.
  for (int i = 0; i < 56; i++) posedge(top);
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

static void frame(Vvideo* top, int show, int square, const char* name) {
  int white = 0;
  int want_white = 0;
  int mismatch = 0;
  for (int i = 0; i < FRAME; i++) {
    posedge(top);
    int x = top->x_q;
    int y = top->y_q;
    int hs = x >= 96;
    int vs = y >= 2;
    int de = (x >= 144 && x < 784 && y >= 35 && y < 515);
    int on = show && de && (glyph_on(x, y) || square_on(x, y, square));
    uint16_t want0 = de ? (on ? WHITE : BLACK) : ctrl(vs, hs);
    uint16_t want1 = de ? want0 : CTRL00;
    if ((int)top->de_q != de || (int)top->hs_q != hs || (int)top->vs_q != vs ||
        top->word0 != want0 || top->word1 != want1 || top->word2 != want1) {
      if (mismatch < 8) {
        fprintf(stderr,
                "FAIL %s i=%d x=%d y=%d de=%u w=%03x want de=%d w=%03x on=%d\n",
                name, i, x, y, top->de_q, top->word0, de, want0, on);
      }
      mismatch++;
    }
    if (on) want_white++;
    if (de && top->word0 == WHITE) white++;
  }
  if (mismatch || white != want_white) {
    fprintf(stderr, "FAIL %s mismatch %d white %d want %d\n",
            name, mismatch, white, want_white);
    fails++;
  } else {
    printf("ok %s white %d\n", name, white);
  }
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  load_font();
  std::memset(cells, 0, sizeof cells);
  auto* top = new Vvideo;
  top->clk27 = 0;
  top->led = 1;
  top->blank = 0;
  top->pix_sim = 0;
  top->screen_we = 0;
  top->screen_bit = 0;
  top->armed = 0;
  top->text_we = 0;
  top->text_word = 0;
  top->eval();

  put_count(top, 1);
  frame(top, 0, 0, "unarmed");

  top->armed = 1;
  for (int i = 0; i < 8; i++) posedge(top);
  frame(top, 1, 0, "0001");

  top->screen_bit = 1;
  top->screen_we = 1;
  posedge(top);
  top->screen_we = 0;
  posedge(top);
  posedge(top);
  frame(top, 1, 1, "0001+square");

  put_count(top, 2);
  frame(top, 1, 1, "0002+square");

  put_count(top, 10);
  frame(top, 1, 1, "0010+square");

  put_count(top, 10000);
  frame(top, 1, 1, "0000+square");

  // Digits and the square stay. Blanking hides them. Release shows
  // the same 0000 plus the square, the phase already stored.
  top->blank = 1;
  to_frame(top);
  frame(top, 0, 0, "blanked");
  top->blank = 0;
  to_frame(top);
  frame(top, 1, 1, "released");
  if (fails) {
    fprintf(stderr, "FAIL %d\n", fails);
    return 1;
  }
  printf("ok text 0001, 0002, 0010, then 10000 as 0000\n");
  return 0;
}
