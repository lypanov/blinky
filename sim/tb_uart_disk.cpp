// UART-disk bench. Counts bridge-clock cycles, LED edges, and halt.
// The period is between edges. The transfer only moves the first one.
#include "Vuart_disk_top.h"
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
  uint64_t max_cycles = 80000000;
  uint64_t period = 0;
  // Same poll window as the NOR bench. The accumulated error stays
  // inside one poll of Kernel.Time.
  uint64_t slack = 0;
  int edges_needed = 3;
  int expect_halt = 0;
  int reset_cycles = 32;
  uint32_t min_pc = 0;
  int watch = 0;
  int press = 0;
  uint64_t hold_cycles = 0;
  int bit_clocks = 210;
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
    else if (!strcmp(argv[i], "--slack")) slack = strtoull(need("--slack"), nullptr, 10);
    else if (!strcmp(argv[i], "--edges")) edges_needed = atoi(need("--edges"));
    else if (!strcmp(argv[i], "--expect-halt")) expect_halt = 1;
    else if (!strcmp(argv[i], "--reset")) reset_cycles = atoi(need("--reset"));
    else if (!strcmp(argv[i], "--min-pc")) min_pc = strtoul(need("--min-pc"), nullptr, 0);
    else if (!strcmp(argv[i], "--watch")) watch = 1;
    else if (!strcmp(argv[i], "--press")) press = 1;
    else if (!strcmp(argv[i], "--hold-cycles")) hold_cycles = strtoull(need("--hold-cycles"), nullptr, 10);
    else if (!strcmp(argv[i], "--bit-clocks")) bit_clocks = atoi(need("--bit-clocks"));
    else {
      fprintf(stderr, "unknown %s\n", argv[i]);
      return 2;
    }
  }

  auto* top = new Vuart_disk_top;
  top->clock = 0;
  top->reset = 1;
  top->host_rx = 1;
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
  int screen_pulses = 0;
  int prev_screen = 0;
  for (; cycle < max_cycles; cycle++) {
    step();
    if (top->mem_write && (top->mem_addr == 0xFFFFFFB0u ||
                           top->mem_addr == 0xFFFFFFB8u ||
                           top->mem_addr == 0xFFFFFFBCu ||
                           top->mem_addr == 0xFFFFFFC0u ||
                           top->mem_addr == 0xFFFFFFC4u)) {
      fprintf(stderr, "FAIL store to %08x fell through at cycle %llu\n",
              (unsigned)top->mem_addr, (unsigned long long)cycle);
      failed = 1;
      break;
    }
    if (watch && top->mem_write && top->mem_addr < 0x100u) {
      printf("W cycle %llu pc %08x addr %08x r2 %08x r5 %08x r9 %08x\n",
             (unsigned long long)cycle, top->pc, top->mem_addr, top->r2,
             top->r5, top->r9);
    }
    if (watch && (cycle % 200000ull) == 0) {
      printf("T cycle %llu pc %08x r2 %08x r5 %08x r9 %08x mask %010llx\n",
             (unsigned long long)cycle, top->pc, top->r2, top->r5, top->r9,
             (unsigned long long)top->mask);
    }
    int screen = top->screen_we ? 1 : 0;
    if (screen && !prev_screen) screen_pulses++;
    prev_screen = screen;
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

  printf("DONE cycles %llu edges %zu saw_led %d halt %llu screen %d\n",
         (unsigned long long)cycle, edges.size(), saw_led,
         (unsigned long long)halt_at, screen_pulses);

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
      uint64_t acc = 0;
      for (size_t i = 1; i < edges.size(); i++) {
        uint64_t d = edges[i] - edges[i - 1];
        uint64_t diff = d > period ? d - period : period - d;
        acc += d;
        if (diff > slack) {
          fprintf(stderr, "FAIL period %llu wanted %llu slack %llu\n",
                  (unsigned long long)d, (unsigned long long)period,
                  (unsigned long long)slack);
          failed = 1;
          break;
        }
      }
      if (!failed) {
        uint64_t want = period * (edges.size() - 1);
        uint64_t ad = acc > want ? acc - want : want - acc;
        if (ad > slack) {
          fprintf(stderr, "FAIL accumulated %llu wanted %llu slack %llu\n",
                  (unsigned long long)acc, (unsigned long long)want,
                  (unsigned long long)slack);
          failed = 1;
        }
      }
    }
    // The screen store is the instruction after the LED store. A run
    // that stops on the first edge has not seen it yet.
    if (screen_pulses < 1 && !(press && edges.size() == 1)) {
      fprintf(stderr, "FAIL no store to the screen\n");
      failed = 1;
    }
    if (!edges.empty()) {
      uint64_t mask = top->mask;
      if (mask != 0xffffffffffULL || top->r5 != 0 || top->r9 != 0) {
        fprintf(stderr, "FAIL mask/r5/r9 at the edge\n");
        failed = 1;
      }
      if (min_pc && top->pc < min_pc) {
        fprintf(stderr, "FAIL pc %08x is still in the bootstrap\n", top->pc);
        failed = 1;
      }
    }
  }
  // 0x01 latches the same switch bit as the button. The LED stays on
  // across three periods, and 0x00 lets the same period resume.
  if (press && !failed && !expect_halt) {
    if (hold_cycles == 0) hold_cycles = period * 3;
    if (edges.size() != 1 || !top->led || hold_cycles == 0 || bit_clocks < 8) {
      fprintf(stderr, "FAIL press wants one rising edge and a hold\n");
      failed = 1;
    } else {
      int held_led = 1;
      prev = held_led;
      int edges_during = 0;
      int screen_during = 0;
      for (int guard = 0; screen_pulses < 1 && guard < 4000 && !failed; guard++) {
        cycle++;
        step();
        int screen = top->screen_we ? 1 : 0;
        if (screen && !prev_screen) screen_pulses++;
        prev_screen = screen;
        int led = top->led ? 1 : 0;
        if (led != prev) {
          fprintf(stderr, "FAIL edge before the screen store at %llu\n",
                  (unsigned long long)cycle);
          failed = 1;
        }
        prev = led;
      }
      if (screen_pulses < 1) {
        fprintf(stderr, "FAIL no store to the screen before the press\n");
        failed = 1;
      }
      if (failed) {
        top->final();
        delete top;
        return failed;
      }
      auto watch = [&]() -> int {
        if (top->mem_write && (top->mem_addr == 0xFFFFFFB0u ||
                               top->mem_addr == 0xFFFFFFB8u ||
                               top->mem_addr == 0xFFFFFFBCu ||
                               top->mem_addr == 0xFFFFFFC0u ||
                               top->mem_addr == 0xFFFFFFC4u)) {
          fprintf(stderr, "FAIL store to %08x during press\n", (unsigned)top->mem_addr);
          return 1;
        }
        int screen = top->screen_we ? 1 : 0;
        if (screen && !prev_screen) screen_during++;
        prev_screen = screen;
        int led = top->led ? 1 : 0;
        if (led != prev) edges_during++;
        if (led != held_led) {
          fprintf(stderr, "FAIL led changed during press at %llu\n",
                  (unsigned long long)cycle);
          return 1;
        }
        prev = led;
        return 0;
      };
      // Two bridge clocks are one cpu clock. The decoder counts cpu clocks.
      auto cpu_bits = [&](int level, int ncpu) -> int {
        top->host_rx = level;
        for (int i = 0; i < ncpu * 2; i++) {
          cycle++;
          step();
          if (watch()) return 1;
        }
        return 0;
      };
      auto send = [&](uint8_t byte) -> int {
        if (cpu_bits(0, bit_clocks)) return 1;
        for (int b = 0; b < 8; b++) {
          if (cpu_bits((byte >> b) & 1, bit_clocks)) return 1;
        }
        if (cpu_bits(1, bit_clocks)) return 1;
        if (cpu_bits(1, bit_clocks)) return 1;
        return 0;
      };
      printf("PRESS 01 at cycle %llu\n", (unsigned long long)cycle);
      if (send(0x01)) failed = 1;
      if (!failed) {
        printf("HOLD start %llu for %llu\n",
               (unsigned long long)cycle, (unsigned long long)hold_cycles);
        for (uint64_t n = 0; n < hold_cycles; n++) {
          cycle++;
          step();
          if (watch()) {
            failed = 1;
            break;
          }
        }
      }
      printf("HOLD edges %d screen %d led %d\n", edges_during, screen_during, held_led);
      if (!failed && (edges_during || screen_during)) {
        fprintf(stderr, "FAIL blink advanced while 0x01 was latched\n");
        failed = 1;
      }
      if (!failed) {
        printf("RELEASE 00 at cycle %llu\n", (unsigned long long)cycle);
        if (send(0x00)) failed = 1;
      }
      if (!failed) {
        uint64_t released = cycle;
        std::vector<uint64_t> resume;
        uint64_t limit = released + (period + slack) * 2 + 4096;
        while (resume.size() < 2 && cycle < limit) {
          cycle++;
          step();
          int led = top->led ? 1 : 0;
          if (led != prev) {
            resume.push_back(cycle);
            printf("EDGE resume %zu cycle %llu led %d\n",
                   resume.size(), (unsigned long long)cycle, led);
          }
          prev = led;
          int screen = top->screen_we ? 1 : 0;
          if (screen && !prev_screen) screen_pulses++;
          prev_screen = screen;
        }
        if (resume.size() < 2) {
          fprintf(stderr, "FAIL resume saw %zu edges\n", resume.size());
          failed = 1;
        } else {
          uint64_t gap = resume[1] - resume[0];
          uint64_t diff = gap > period ? gap - period : period - gap;
          uint64_t first = resume[0] - released;
          printf("RESUME first %llu gap %llu\n",
                 (unsigned long long)first, (unsigned long long)gap);
          if (diff > slack) {
            fprintf(stderr, "FAIL resume gap %llu wanted %llu slack %llu\n",
                    (unsigned long long)gap, (unsigned long long)period,
                    (unsigned long long)slack);
            failed = 1;
          }
          if (first > period + slack) {
            fprintf(stderr, "FAIL first edge %llu after release, period %llu\n",
                    (unsigned long long)first, (unsigned long long)period);
            failed = 1;
          }
          if (screen_pulses < 2) {
            fprintf(stderr, "FAIL screen did not resume\n");
            failed = 1;
          }
        }
      }
    }
  }
  top->final();
  delete top;
  return failed;
}
