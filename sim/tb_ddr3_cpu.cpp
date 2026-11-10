// Verilator witness for the DDR3 CPU images against Ddr3UserModel.
// Cycles are pclk. No waveform. Prints the LED edges, the final PC,
// R5, R9, and the check mask.

#include "VCPUSimTop.h"
#include "VCPUSimTop___024root.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static uint32_t cpu_reg(VCPUSimTop* top, int i) {
  auto* r = top->rootp;
  switch (i) {
    case 5: return r->CPUSimTop__DOT__cpu__DOT__regs_5;
    case 9: return r->CPUSimTop__DOT__cpu__DOT__regs_9;
    default: return 0;
  }
}

static uint64_t cpu_mask(VCPUSimTop* top) {
  // The arm result is the wrapper port. The old internal checkMask
  // register is not in this netlist.
  return top->io_mask;
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  int max_cycles = 120000;
  int min_edges = -1;
  int expect_period = -1;
  int expect_r5_set = 0;
  uint32_t expect_r5 = 0;
  int expect_r9_set = 0;
  uint32_t expect_r9 = 0;
  int expect_mask_set = 0;
  uint64_t expect_mask = 0;
  int expect_pc_lo = -1;
  int expect_pc_hi = -1;
  int expect_first = -1;

  for (int i = 1; i < argc; i++) {
    auto need = [&](const char* name) -> const char* {
      if (i + 1 >= argc) {
        std::fprintf(stderr, "missing %s\n", name);
        std::exit(2);
      }
      return argv[++i];
    };
    if (!std::strcmp(argv[i], "--cycles")) max_cycles = std::atoi(need("--cycles"));
    else if (!std::strcmp(argv[i], "--edges")) min_edges = std::atoi(need("--edges"));
    else if (!std::strcmp(argv[i], "--period")) expect_period = std::atoi(need("--period"));
    else if (!std::strcmp(argv[i], "--r5")) {
      expect_r5 = std::strtoul(need("--r5"), nullptr, 16);
      expect_r5_set = 1;
    } else if (!std::strcmp(argv[i], "--r9")) {
      expect_r9 = std::strtoul(need("--r9"), nullptr, 16);
      expect_r9_set = 1;
    } else if (!std::strcmp(argv[i], "--mask")) {
      expect_mask = std::strtoull(need("--mask"), nullptr, 16);
      expect_mask_set = 1;
    }     else if (!std::strcmp(argv[i], "--pc")) {
      expect_pc_lo = std::strtol(need("--pc"), nullptr, 16);
      expect_pc_hi = expect_pc_lo + 8;
    } else if (!std::strcmp(argv[i], "--first")) {
      expect_first = std::atoi(need("--first"));
    } else if (argv[i][0] == '+') {
      // plusarg for the model
    } else {
      std::fprintf(stderr, "unknown arg %s\n", argv[i]);
      return 2;
    }
  }

  VCPUSimTop top;
  top.clock = 0;
  top.reset = 1;
  top.io_btnPressed = 0;
  auto tick = [&]() {
    top.clock = 0;
    top.eval();
    top.clock = 1;
    top.eval();
  };
  // Same reset accounting as tb_blink2: four reset clocks, release,
  // one settling clock that is not part of the measured count.
  for (int i = 0; i < 4; i++)
    tick();
  top.reset = 0;
  tick();

  int prev = top.io_led ? 1 : 0;
  std::vector<int> edges;
  int cycle = 0;
  for (; cycle < max_cycles; cycle++) {
    tick();
    int led = top.io_led ? 1 : 0;
    if (led != prev) {
      edges.push_back(cycle);
      std::printf("[LED] cycle=%d %d->%d pc=%08x\n", cycle, prev, led,
                  (unsigned)top.io_pc);
      prev = led;
      if (min_edges > 0 && (int)edges.size() >= min_edges)
        break;
    }
  }

  uint32_t pc = top.io_pc;
  uint32_t r5 = cpu_reg(&top, 5);
  uint32_t r9 = cpu_reg(&top, 9);
  uint64_t mask = cpu_mask(&top);
  std::printf("END cycle=%d edges=%zu pc=%08x r5=%08x r9=%08x mask=%llx\n",
              cycle, edges.size(), pc, r5, r9, (unsigned long long)mask);
  if (edges.size() >= 2) {
    std::printf("periods");
    for (size_t i = 1; i < edges.size(); i++)
      std::printf(" %d", edges[i] - edges[i - 1]);
    std::printf("\nfirst_edge %d\n", edges[0]);
  }

  int rc = 0;
  if (min_edges == 0 && !edges.empty()) {
    std::printf("FAIL wanted 0 LED edges\n");
    rc = 1;
  }
  if (min_edges > 0 && (int)edges.size() < min_edges) {
    std::printf("FAIL wanted %d LED edges\n", min_edges);
    rc = 1;
  }
  if (expect_period >= 0 && edges.size() >= 2) {
    int period = edges[1] - edges[0];
    if (period != expect_period) {
      std::printf("FAIL period %d want %d\n", period, expect_period);
      rc = 1;
    }
  }
  if (expect_r5_set && r5 != expect_r5) {
    std::printf("FAIL r5 %08x want %08x\n", r5, expect_r5);
    rc = 1;
  }
  if (expect_r9_set && r9 != expect_r9) {
    std::printf("FAIL r9 %08x want %08x\n", r9, expect_r9);
    rc = 1;
  }
  if (expect_mask_set && mask != expect_mask) {
    std::printf("FAIL mask %llx want %llx\n",
                (unsigned long long)mask, (unsigned long long)expect_mask);
    rc = 1;
  }
  if (expect_pc_lo >= 0 && ((int)pc < expect_pc_lo || (int)pc >= expect_pc_hi)) {
    std::printf("FAIL pc %08x not in [%x,%x)\n", pc, expect_pc_lo, expect_pc_hi);
    rc = 1;
  }
  if (expect_first >= 0) {
    if (edges.empty() || edges[0] != expect_first) {
      std::printf("FAIL first edge %s want %d\n",
                  edges.empty() ? "none" : std::to_string(edges[0]).c_str(),
                  expect_first);
      rc = 1;
    }
  }
  return rc;
}
