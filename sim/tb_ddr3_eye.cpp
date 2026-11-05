// Command-port checks for Ddr3UserModel: BC4 lanes, DM, HOLD, WLOADN.
// The CPU images cover the same eyes from the bridge. This drives the
// model the way Ddr3Bridge does, without the prologue in front.

#include "VDdr3UserModel.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

static VDdr3UserModel* top;

static void tick() {
  top->clk = 0;
  top->eval();
  top->clk = 1;
  top->eval();
}

static void wait_idle() {
  for (int i = 0; i < 40 && top->busy; i++)
    tick();
  if (top->busy) {
    std::printf("busy stuck\n");
    std::exit(1);
  }
}

static void wait_calib() {
  for (int i = 0; i < 200 && !top->calib; i++)
    tick();
  if (!top->calib) {
    std::printf("calib never rose\n");
    std::exit(1);
  }
  wait_idle();
}

static void write_col(uint32_t col, uint16_t data) {
  wait_idle();
  top->addr = col;
  top->din = data;
  top->rd = 0;
  top->refresh = 0;
  top->wr = 1;
  tick();
  top->wr = 0;
  wait_idle();
}

static uint16_t read_col(uint32_t col) {
  wait_idle();
  top->addr = col;
  top->rd = 1;
  top->wr = 0;
  top->refresh = 0;
  tick();
  top->rd = 0;
  uint16_t got = 0;
  bool saw = false;
  for (int i = 0; i < 40; i++) {
    tick();
    if (top->data_ready) {
      got = top->dout;
      saw = true;
      break;
    }
  }
  if (!saw) {
    std::printf("no data_ready for col %x\n", col);
    std::exit(1);
  }
  wait_idle();
  return got;
}

static uint32_t read_word(uint32_t byte_addr) {
  uint32_t col = byte_addr >> 1;
  uint16_t lo = read_col(col);
  uint16_t hi = read_col(col + 1);
  return (uint32_t)lo | ((uint32_t)hi << 16);
}

static uint16_t merge_byte(uint16_t old, int lane_bit0, uint8_t byte) {
  if (lane_bit0)
    return (uint16_t)((byte << 8) | (old & 0x00FF));
  return (uint16_t)((old & 0xFF00) | byte);
}

// Bridge byte store: read the half, merge one byte, write it back.
static void stb(uint32_t byte_addr, uint8_t byte) {
  uint32_t col = byte_addr >> 1;
  uint16_t old = read_col(col);
  write_col(col, merge_byte(old, byte_addr & 1, byte));
}

static int g_fail;

static void expect_eq(const char* name, uint32_t got, uint32_t want) {
  if (got != want) {
    std::printf("FAIL %s got %08x want %08x\n", name, got, want);
    g_fail++;
  } else {
    std::printf("ok   %s %08x\n", name, got);
  }
}

static void write_word(uint32_t byte_addr, uint32_t word) {
  write_col(byte_addr >> 1, (uint16_t)word);
  write_col((byte_addr >> 1) + 1, (uint16_t)(word >> 16));
}

// Cold reader prologue: setup words, then each pattern word and its
// complement, then the alias and the sentinel.
static void cold_prologue() {
  write_word(0x14, 0x50);
  write_word(0x18, 0x70);
  for (int i = 0; i < 32; i++) {
    write_word(0x400 + 4 * i, 1u << i);
    write_word(0x500 + 4 * i, ~((uint32_t)1 << i));
  }
  write_word(0x114, 0x11111111u);
  write_word(0x7F0, 0xA5A5A5A5u);
  uint32_t s5 = 0;
  uint32_t s9 = 0;
  for (int i = 0; i < 32; i++) {
    s5 += read_word(0x400 + 4 * i);
    s9 += read_word(0x500 + 4 * i);
  }
  expect_eq("cold r5", s5, 0xDFAADFAAu);
  expect_eq("cold r9", s9, 0x20532036u);
  expect_eq("mt1", read_word(0x14), 0x50);
  expect_eq("mt2", read_word(0x18), 0x70);
  expect_eq("alias", read_word(0x114), 0x11111111u);
  expect_eq("sentinel", read_word(0x7F0), 0xA5A5A5A5u);
  // CPU beat of the sentinel is A5A5. The Dock's next burst beat is
  // 25A5; the stored partner column is 20A5 (lane 1 only DQ5 spilled).
  expect_eq("partner", read_col(0x3FA), 0x20A5);
}

static void write_pair() {
  // Even word 0x44332211, odd word 0x88776655, one BC4 group.
  write_col(0x200, 0x2211);
  write_col(0x201, 0x4433);
  write_col(0x202, 0x6655);
  write_col(0x203, 0x8877);
}

static void check_pair(uint16_t c0, uint16_t c1, uint16_t c2, uint16_t c3) {
  expect_eq("col0", read_col(0x200), c0);
  expect_eq("col1", read_col(0x201), c1);
  expect_eq("col2", read_col(0x202), c2);
  expect_eq("col3", read_col(0x203), c3);
}

// Four lane bytes, then a neighbour in the same burst, then one byte
// updated. The neighbour and the untouched byte have to survive.
static void byte_walk(bool want_pass) {
  const uint32_t lane = 0x920;
  const uint32_t neigh = 0x924;
  const uint8_t bytes[4] = {0x11, 0x22, 0x33, 0x44};
  for (int i = 0; i < 4; i++)
    stb(lane + i, bytes[i]);
  uint32_t word = read_word(lane);
  write_col(neigh >> 1, 0xA5A5);
  write_col((neigh >> 1) + 1, 0xA5A5);
  stb(lane + 3, 0x77);
  uint32_t kept = read_word(neigh);
  uint32_t updated = read_word(lane);
  // Byte 3 is the top byte. 0x77 there is 0x77332211, and 0x33 stays.
  bool pass = word == 0x44332211 && kept == 0xA5A5A5A5 && updated == 0x77332211;
  std::printf("byte walk word=%08x neigh=%08x updated=%08x\n", word, kept, updated);
  if (pass != want_pass) {
    std::printf("FAIL byte walk pass=%d want %d\n", pass, want_pass);
    g_fail++;
  } else {
    std::printf("ok   byte walk\n");
  }
}

static bool has(int argc, char** argv, const char* name) {
  for (int i = 1; i < argc; i++)
    if (std::string(argv[i]) == name)
      return true;
  return false;
}

// +ddr3_lane0=N / +ddr3_lane1=N are the programmed steps. +ddr3_center is
// the programmed step the data eye is centered on for this place.
static unsigned plus_hex(int argc, char** argv, const char* key, bool* present) {
  std::string prefix = std::string("+") + key + "=";
  for (int i = 1; i < argc; i++) {
    std::string arg(argv[i]);
    if (arg.compare(0, prefix.size(), prefix) == 0) {
      *present = true;
      return std::strtoul(arg.c_str() + prefix.size(), nullptr, 16);
    }
  }
  *present = false;
  return 0;
}

static int plus_int(int argc, char** argv, const char* key, int fallback) {
  std::string prefix = std::string("+") + key + "=";
  for (int i = 1; i < argc; i++) {
    std::string arg(argv[i]);
    if (arg.compare(0, prefix.size(), prefix) == 0)
      return std::atoi(arg.c_str() + prefix.size());
  }
  return fallback;
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  top = new VDdr3UserModel;
  top->clk = 0;
  top->rst_n = 0;
  top->rd = 0;
  top->wr = 0;
  top->refresh = 0;
  top->addr = 0;
  top->din = 0;
  for (int i = 0; i < 4; i++)
    tick();
  top->rst_n = 1;
  wait_calib();

  bool pin_set = false;
  bool clear_set = false;
  const unsigned pin_even = plus_hex(argc, argv, "ddr3_pin_even", &pin_set);
  const unsigned odd_clear = plus_hex(argc, argv, "ddr3_odd_clear", &clear_set);
  const bool nohold = has(argc, argv, "+ddr3_nohold");
  const bool nowload = has(argc, argv, "+ddr3_nowload");
  const bool dm_all = has(argc, argv, "+ddr3_dm_all");
  const bool dm_lane0 = has(argc, argv, "+ddr3_dm_lane0");
  const bool dm_lane1 = has(argc, argv, "+ddr3_dm_lane1");
  const bool shift1 = has(argc, argv, "+ddr3_lane1=12");
  const bool corrupt = has(argc, argv, "+ddr3_corrupt");
  const int center = plus_int(argc, argv, "ddr3_center", 10);
  const int off0 = plus_int(argc, argv, "ddr3_lane0", 10) - center;
  const int off1 = plus_int(argc, argv, "ddr3_lane1", 10) - center;

  if (pin_set) {
    // Cold step-10 line: lane 0 even-word alias, lane 1 only DQ5, and
    // DQ1 can still clear the high half of the odd word.
    if (pin_even == 0x20FF && clear_set && odd_clear == 0x2)
      cold_prologue();
    else {
      std::printf("FAIL unhandled pin mask even=%x clear=%x\n", pin_even, odd_clear);
      return 1;
    }
  } else if (corrupt) {
    write_col(0x10, 0x1234);
    expect_eq("corrupt", read_col(0x10), 0);
  } else if (dm_all) {
    write_col(0x10, 0x1111);
    write_col(0x11, 0x2222);
    expect_eq("dm all beat0", read_col(0x10), 0x2222);
    expect_eq("dm all beat2", read_col(0x12), 0x2222);
    byte_walk(false);
  } else if (dm_lane0) {
    write_col(0x10, 0x2211);
    expect_eq("lane0 only", read_col(0x10), 0x0011);
    byte_walk(false);
  } else if (dm_lane1) {
    write_col(0x10, 0x2211);
    expect_eq("lane1 only", read_col(0x10), 0x2200);
    byte_walk(false);
  } else if (shift1) {
    write_col(0x30, 0x2211);
    expect_eq("shift lane0 stays", read_col(0x30), 0x0011);
    expect_eq("shift lane1 moved", read_col(0x32), 0x2200);
  } else if (nowload) {
    // Aimed at column 0x28. After a read the reload is missing, so the
    // next write is two columns later.
    write_col(0x28, 0x5A74);
    expect_eq("before read", read_col(0x28), 0x5A74);
    write_col(0x28, 0x1111);
    expect_eq("aimed column", read_col(0x28), 0x5A74);
    expect_eq("two later", read_col(0x2A), 0x1111);
    byte_walk(false);
  } else if (nohold) {
    write_pair();
    check_pair(0x2211, 0x4433, 0x2211, 0x4433);
    // An odd column that was written on its own still reads as the even
    // column. One step above the eye would have kept this write.
    write_col(0x16, 0xBEEF);
    expect_eq("isolated odd", read_col(0x16), 0x0000);
    byte_walk(false);
  } else if (off0 == 1 && off1 == 1) {
    // Programmed one step above the eye. On the reader place that is
    // the forced step 10 (+ddr3_center=9). On the ALU place it is step 11.
    write_pair();
    check_pair(0x2211, 0x4433, 0x2211, 0x4433);
    write_col(0x16, 0xBEEF);
    expect_eq("isolated odd kept", read_col(0x16), 0xBEEF);
    byte_walk(false);
  } else if (off0 == -1 && off1 == -1) {
    write_pair();
    check_pair(0x6655, 0x8877, 0x6655, 0x8877);
    byte_walk(false);
  } else if (off0 == 0 && off1 == 1) {
    write_pair();
    check_pair(0x2211, 0x4433, 0x2255, 0x4477);
    byte_walk(false);
  } else if (off0 == 1 && off1 == 0) {
    write_pair();
    check_pair(0x2211, 0x4433, 0x6611, 0x8833);
    byte_walk(false);
  } else if (off0 == 0 && off1 == -1) {
    write_pair();
    check_pair(0x6611, 0x8833, 0x6655, 0x8877);
    byte_walk(false);
  } else if (off0 == -1 && off1 == 0) {
    write_pair();
    check_pair(0x2255, 0x4477, 0x6655, 0x8877);
    byte_walk(false);
  } else if (off0 == 0 && off1 == 0) {
    write_pair();
    check_pair(0x2211, 0x4433, 0x6655, 0x8877);
    // Neighbour column in the same group is not written by a one-beat store.
    expect_eq("untouched", read_col(0x204), 0);
    byte_walk(true);
    write_col(0x28, 0x5A74);
    expect_eq("reload keeps column", read_col(0x28), 0x5A74);
    write_col(0x28, 0x1111);
    expect_eq("reload aimed", read_col(0x28), 0x1111);
    expect_eq("reload not shifted", read_col(0x2A), 0);
  } else {
    std::printf("FAIL unhandled eye off0=%d off1=%d\n", off0, off1);
    return 1;
  }

  if (g_fail) {
    std::printf("%d failures\n", g_fail);
    return 1;
  }
  std::printf("eye pass\n");
  return 0;
}
