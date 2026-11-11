// One frame of the video module, taken at a chosen CPU cycle.
// The sample is word0/word1/word2, the pixel words before the HDMI
// serializer. The active picture is written as a P5 image. The host
// draws the picture it expects and compares the two.
#include "Vvideo.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#ifdef VIDEO_DOCK
// VESA 1024×768, counted from the sync pulse. 24.1875/64.8 = 215/576.
static const int H = 1344;
static const int V = 806;
static const int AW = 1024;
static const int AH = 768;
static const int H0 = 296;
static const int H1 = 1320;
static const int V0 = 35;
static const int V1 = 803;
static const int DOCK_CPU = 215;
static const int DOCK_PIX = 576;
#else
static const int H = 858;
static const int V = 525;
static const int AW = 720;
static const int AH = 480;
static const int H0 = 122;
static const int H1 = 842;
static const int V0 = 36;
static const int V1 = 516;
static const int DOCK_CPU = 43;
static const int DOCK_PIX = 48;
#endif
static const int FRAME = H * V;
static const uint16_t BLACK = 0b0111110000;
static const uint16_t WHITE = 0b1011110000;
#ifdef VIDEO_DOCK
// Ten bitmap rows, word 1764 then +16, bits 22..31.
static const int SQ_N = 10;
static const int SQ_WORD0 = 1764;
static const int SQ_STEP = 16;
static const uint32_t SQ_DATA = 0xFFC00000u;
#else
// Five bitmap rows, word 442 then +8, bits 11..15.
static const int SQ_N = 5;
static const int SQ_WORD0 = 442;
static const int SQ_STEP = 8;
static const uint32_t SQ_DATA = 0x0000F800u;
#endif

static void fail(const char* msg) {
  fprintf(stderr, "FAIL %s\n", msg);
  exit(1);
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  const char* board = nullptr;
  const char* out_path = nullptr;
  int target = -1;
  int led_cycle = -1;
  int arm_cycle = 2;
  int store_cycle = -1;
  int blank_cycle = -1;
  int status_cycle = -1;
  int status_word = 0;

  for (int i = 1; i < argc; i++) {
    auto need = [&](const char* name) -> const char* {
      if (i + 1 >= argc) {
        fprintf(stderr, "missing %s\n", name);
        exit(2);
      }
      return argv[++i];
    };
    if (!strcmp(argv[i], "--board")) board = need("--board");
    else if (!strcmp(argv[i], "--out")) out_path = need("--out");
    else if (!strcmp(argv[i], "--cycle")) target = atoi(need("--cycle"));
    else if (!strcmp(argv[i], "--led-cycle")) led_cycle = atoi(need("--led-cycle"));
    else if (!strcmp(argv[i], "--arm-cycle")) arm_cycle = atoi(need("--arm-cycle"));
    else if (!strcmp(argv[i], "--store-cycle")) store_cycle = atoi(need("--store-cycle"));
    else if (!strcmp(argv[i], "--blank-cycle")) blank_cycle = atoi(need("--blank-cycle"));
    else if (!strcmp(argv[i], "--status-cycle")) status_cycle = atoi(need("--status-cycle"));
    else if (!strcmp(argv[i], "--status-word")) status_word = (int)strtol(need("--status-word"), nullptr, 0);
    else {
      fprintf(stderr, "unknown %s\n", argv[i]);
      return 2;
    }
  }
  if (!board || !out_path || target < 1) {
    fprintf(stderr, "need --board nano|dock --cycle N --out file.ppm\n");
    return 2;
  }

  int cpu_per = 0;
  int pix_per = 0;
  if (!strcmp(board, "nano")) {
#ifdef VIDEO_DOCK
    fprintf(stderr, "this binary is the Dock 1024x768 timing\n");
    return 2;
#endif
    // 13.5 MHz CPU, 27 MHz pixel clock.
    cpu_per = 1;
    pix_per = 2;
  } else if (!strcmp(board, "dock")) {
#ifndef VIDEO_DOCK
    fprintf(stderr, "this binary is the Nano 720x480 timing\n");
    return 2;
#endif
    // 24.1875 MHz CPU. The Dock pixel clock is 64.8 MHz, 215/576.
    cpu_per = DOCK_CPU;
    pix_per = DOCK_PIX;
  } else {
    fprintf(stderr, "board %s\n", board);
    return 2;
  }
  auto past = [&](int edge) {
    return edge >= 0 && edge > target;
  };
  int store_last = store_cycle < 0 ? -1 : store_cycle + SQ_N - 1;
  if (past(led_cycle) || past(arm_cycle) || past(store_last) || past(blank_cycle) ||
      past(status_cycle)) {
    fprintf(stderr, "stimulus cycle is after the capture cycle\n");
    return 2;
  }

  auto* top = new Vvideo;
  top->clk27 = 0;
  top->led = 0;
  top->blank = 0;
  top->pix_sim = 0;
#ifdef FRAME_SQUARE
  top->screen_we = 0;
  top->screen_bit = 0;
  top->bmp_data = 0;
  top->bmp_word = 0;
  top->armed = 0;
  top->status_we = 0;
  top->status_in = 0;
  top->clk_cpu = 0;
#endif
#ifdef FRAME_TEXT
  top->text_we = 0;
  top->text_word = 0;
#endif
  top->eval();

  int cpu_cycle = 0;
  int acc = 0;
  auto cpu_edge = [&]() {
    int c = cpu_cycle + 1;
    top->led = (led_cycle >= 0 && c >= led_cycle) ? 1 : 0;
    top->blank = (blank_cycle >= 0 && c >= blank_cycle) ? 1 : 0;
#ifdef FRAME_SQUARE
    top->armed = (arm_cycle >= 0 && c >= arm_cycle) ? 1 : 0;
    int k = store_cycle < 0 ? -1 : c - store_cycle;
    int writing = k >= 0 && k < SQ_N;
    top->screen_bit = 0;
    top->screen_we = writing ? 1 : 0;
    top->bmp_word = writing ? (SQ_WORD0 + k * SQ_STEP) : 0;
    top->bmp_data = writing ? SQ_DATA : 0;
    top->status_in = status_word & 0x1FF;
    top->status_we = (status_cycle >= 0 && c == status_cycle) ? 1 : 0;
    top->clk_cpu = 0;
    top->eval();
    top->clk_cpu = 1;
    top->eval();
    top->screen_we = 0;
    top->bmp_data = 0;
    top->status_we = 0;
#endif
    cpu_cycle = c;
  };
  auto pix = [&]() {
    top->pix_sim = 0;
    top->eval();
    top->pix_sim = 1;
    top->eval();
    acc += cpu_per;
    if (acc >= pix_per) {
      acc -= pix_per;
      cpu_edge();
    }
  };

  std::vector<uint8_t> img(AW * AH, 2);
  std::vector<uint8_t> wrote(AW * AH, 0);
  int seen = 0;
  int white = 0;
  bool capturing = false;
  int got = 0;
  int frame_cpu = 0;
  int guard = 0;
  while (got < FRAME) {
    pix();
    if (++guard > FRAME * 4) fail("no frame");
    if (!capturing) {
      if (cpu_cycle >= target && top->x_q == 0 && top->y_q == 0) {
        capturing = true;
        frame_cpu = cpu_cycle;
      } else {
        continue;
      }
    }
    int x = top->x_q;
    int y = top->y_q;
    int de = (x >= H0 && x < H1 && y >= V0 && y < V1);
    if ((int)top->de_q != de) fail("de");
    if (de) {
      if (top->word0 != top->word1 || top->word0 != top->word2) fail("channels");
      if (top->word0 != BLACK && top->word0 != WHITE) fail("pixel word");
      int ax = x - H0;
      int ay = y - V0;
      int i = ay * AW + ax;
      if (wrote[i]) fail("pixel twice");
      wrote[i] = 1;
      img[i] = top->word0 == WHITE ? 255 : 0;
      if (img[i]) white++;
      seen++;
    }
    got++;
  }
  if (seen != AW * AH) {
    fprintf(stderr, "FAIL active %d\n", seen);
    return 1;
  }
  for (int i = 0; i < AW * AH; i++) {
    if (!wrote[i]) fail("missing pixel");
  }

  FILE* f = fopen(out_path, "wb");
  if (!f) {
    perror(out_path);
    return 1;
  }
  if (fprintf(f, "P5\n%d %d\n255\n", AW, AH) < 0) fail("write");
  if (fwrite(img.data(), 1, img.size(), f) != img.size()) fail("write");
  fclose(f);
  printf("ok %s cycle %d frame_cpu %d white %d\n", board, target, frame_cpu, white);
  return 0;
}
