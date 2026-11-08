// Disk-boot bench. Counts bridge-clock cycles, LED edges, and halt.
#include "Vdisk_boot_top.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static vluint64_t main_time = 0;
double sc_time_stamp() { return static_cast<double>(main_time); }

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  uint64_t max_cycles = 40000000;
  uint64_t period = 0;
  int edges_needed = 3;
  int expect_halt = 0;
  int reset_cycles = 32;
  for (int i = 1; i < argc; i++) {
    auto need = [&](const char* name) -> const char* {
      if (i + 1 >= argc) {
        fprintf(stderr, "missing %s\n", name);
        exit(2);
      }
      return argv[++i];
    };
    if (argv[i][0] == '+') continue;
    if (!strcmp(argv[i], "--cycles")) max_cycles = strtoull(need("--cycles"), nullptr, 10);
    else if (!strcmp(argv[i], "--period")) period = strtoull(need("--period"), nullptr, 10);
    else if (!strcmp(argv[i], "--edges")) edges_needed = atoi(need("--edges"));
    else if (!strcmp(argv[i], "--expect-halt")) expect_halt = 1;
    else if (!strcmp(argv[i], "--reset")) reset_cycles = atoi(need("--reset"));
    else {
      fprintf(stderr, "unknown %s\n", argv[i]);
      return 2;
    }
  }

  auto* top = new Vdisk_boot_top;
  top->clock = 0;
  top->reset = 1;
  std::vector<uint64_t> edges;
  int prev = 0;
  int saw_led = 0;
  uint64_t halt_at = 0;
  uint64_t cycle = 0;

  auto step = [&]() {
    top->clock = 0;
    top->eval();
    main_time++;
    top->clock = 1;
    top->eval();
    main_time++;
  };

  for (int i = 0; i < reset_cycles; i++) step();
  top->reset = 0;

  int failed = 0;
  for (; cycle < max_cycles; cycle++) {
    step();
    int led = top->led ? 1 : 0;
    if (led) saw_led = 1;
    if (cycle > 0 && led != prev) {
      edges.push_back(cycle);
      printf("EDGE %zu cycle %llu led %d mask %010llx r5 %08x r9 %08x halted %d pc %08x\n",
             edges.size(),
             (unsigned long long)cycle,
             led,
             (unsigned long long)top->mask,
             top->r5,
             top->r9,
             top->halted ? 1 : 0,
             top->pc);
      if ((int)edges.size() >= edges_needed) break;
    }
    prev = led;
    if (top->halted && halt_at == 0) {
      halt_at = cycle;
      printf("HALT cycle %llu led %d pc %08x\n",
             (unsigned long long)cycle, led, top->pc);
      if (expect_halt) break;
    }
  }

  printf("DONE cycles %llu edges %zu saw_led %d halt %llu\n",
         (unsigned long long)cycle, edges.size(), saw_led,
         (unsigned long long)halt_at);

  if (expect_halt) {
    if (!halt_at || saw_led) {
      fprintf(stderr, "FAIL expected a dark halt\n");
      failed = 1;
    }
  } else {
    if (halt_at) {
      fprintf(stderr, "FAIL halted\n");
      failed = 1;
    }
    if ((int)edges.size() < edges_needed) {
      fprintf(stderr, "FAIL only %zu edges\n", edges.size());
      failed = 1;
    }
    if (period && edges.size() >= 2) {
      for (size_t i = 1; i < edges.size(); i++) {
        uint64_t d = edges[i] - edges[i - 1];
        if (d != period) {
          fprintf(stderr, "FAIL period %llu wanted %llu\n",
                  (unsigned long long)d, (unsigned long long)period);
          failed = 1;
          break;
        }
      }
    }
    if (!edges.empty()) {
      uint64_t mask = top->mask;
      if (mask != 0xffffffffffULL || top->r5 != 0 || top->r9 != 0) {
        fprintf(stderr, "FAIL mask/r5/r9 at the edge\n");
        failed = 1;
      }
    }
  }
  top->final();
  delete top;
  return failed;
}
