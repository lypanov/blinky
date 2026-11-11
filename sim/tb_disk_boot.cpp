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

static int fell_through(uint32_t addr) {
  if (addr == 0xFFFFFFACu || addr == 0xFFFFFFB0u || addr == 0xFFFFFFB8u ||
      addr == 0xFFFFFFBCu || addr == 0xFFFFFFC0u || addr == 0xFFFFFFC4u)
    return 1;
  // Both bitmap windows, 0xFFFE0000..0xFFFEFFFF.
  return (addr & 0xFFFF0000u) == 0xFFFE0000u;
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  // The boot file is about 40 KB behind a 20-byte header. Each NOR
  // word is one SPI read, about 5600 bridge clocks, so ingesting the
  // file is past 60 million clocks before LoadFromDisk starts.
  // The 4K holds each stage for 300000 stack decrements. The started
  // code is held three times. One hold is 27e6 bridge clocks, 1.000 s
  // at 27 MHz. Ten holds are 270e6 clocks before the NOR reads and
  // the core copy.
  uint64_t max_cycles = 800000000;
  uint64_t period = 0;
  // After switch_after gaps the edge uses period2. Zero leaves every
  // gap on period. Blink polls Kernel.Time, so an edge lands up to one
  // poll after the tick. The gaps add up to the counter: the accumulated
  // error stays inside one poll.
  uint64_t period2 = 0;
  int switch_after = 0;
  uint64_t slack = 0;
  int edges_needed = 3;
  int expect_halt = 0;
  int expect_no_arm = 0;
  int exhaust_rises = 0;
  int reset_cycles = 32;
  int press = 0;
  uint64_t hold_cycles = 0;
  int expect_status = -1;
  std::vector<int> expect_seq;
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
    else if (!strcmp(argv[i], "--period2")) period2 = strtoull(need("--period2"), nullptr, 10);
    else if (!strcmp(argv[i], "--switch-after")) switch_after = atoi(need("--switch-after"));
    else if (!strcmp(argv[i], "--slack")) slack = strtoull(need("--slack"), nullptr, 10);
    else if (!strcmp(argv[i], "--edges")) edges_needed = atoi(need("--edges"));
    else if (!strcmp(argv[i], "--expect-halt")) expect_halt = 1;
    else if (!strcmp(argv[i], "--expect-no-arm")) expect_no_arm = 1;
    else if (!strcmp(argv[i], "--exhaust-rises")) exhaust_rises = atoi(need("--exhaust-rises"));
    else if (!strcmp(argv[i], "--reset")) reset_cycles = atoi(need("--reset"));
    else if (!strcmp(argv[i], "--press")) press = 1;
    else if (!strcmp(argv[i], "--hold-cycles")) hold_cycles = strtoull(need("--hold-cycles"), nullptr, 10);
    else if (!strcmp(argv[i], "--expect-status")) expect_status = (int)strtol(need("--expect-status"), nullptr, 0);
    else if (!strcmp(argv[i], "--status-seq")) {
      const char* spec = need("--status-seq");
      expect_seq.clear();
      while (*spec) {
        char* end = nullptr;
        long v = strtol(spec, &end, 0);
        if (end == spec) {
          fprintf(stderr, "bad status-seq\n");
          return 2;
        }
        expect_seq.push_back((int)v);
        spec = (*end == ',') ? end + 1 : end;
      }
    }
    else {
      fprintf(stderr, "unknown %s\n", argv[i]);
      return 2;
    }
  }

  auto* top = new Vdisk_boot_top;
  top->clock = 0;
  top->reset = 1;
  top->btn_n = 1;
  std::vector<uint64_t> edges;
  int prev = 0;
  int saw_led = 0;
  int saw_arm = 0;
  int rises = 0;
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
  int status_writes = 0;
  int saw_mode = 0;
  int mem_before_status = 0;
  int status_last = -1;
  std::vector<int> status_seq;
  for (; cycle < max_cycles; cycle++) {
    step();
    if (top->mem_write && fell_through(top->mem_addr)) {
      fprintf(stderr, "FAIL store to %08x fell through at cycle %llu\n",
              (unsigned)top->mem_addr, (unsigned long long)cycle);
      failed = 1;
      break;
    }
    if (status_writes == 0 && top->mem_write) mem_before_status = 1;
    if (top->status_we) {
      int word = top->status_word & 0x1ff;
      if (status_writes == 0 && word != 0x001) {
        fprintf(stderr, "FAIL first status store %x\n", word);
        failed = 1;
        break;
      }
      if (word != status_last) {
        status_seq.push_back(word);
        status_last = word;
        printf("STATUS %zu cycle %llu word %03x\n",
               status_seq.size(), (unsigned long long)cycle, word);
      }
      if (word & 0x100) saw_mode = 1;
      status_writes++;
    }
    int screen = top->screen_we ? 1 : 0;
    if (screen && !prev_screen) screen_pulses++;
    prev_screen = screen;
    int led = top->led ? 1 : 0;
    if (led) saw_led = 1;
    if (top->armed) saw_arm = 1;
    if (cycle > 0 && led != prev) {
      if (led && !prev) rises++;
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
      if (exhaust_rises == 0 && (int)edges.size() >= edges_needed) break;
    }
    prev = led;
    if (top->halted && halt_at == 0) {
      halt_at = cycle;
      printf("HALT cycle %llu led %d pc %08x\n",
             (unsigned long long)cycle, led, top->pc);
      if (expect_halt || exhaust_rises) break;
    }
  }

  printf("DONE cycles %llu edges %zu saw_led %d halt %llu screen %d status %d mode %d\n",
         (unsigned long long)cycle, edges.size(), saw_led,
         (unsigned long long)halt_at, screen_pulses, status_writes, saw_mode);
  if (!status_writes || mem_before_status) {
    fprintf(stderr, "FAIL status store count %d mem-before %d\n",
            status_writes, mem_before_status);
    failed = 1;
  } else if (!expect_halt && !saw_mode) {
    fprintf(stderr, "FAIL Blink did not set status bit 8\n");
    failed = 1;
  }
  if (!failed && expect_status >= 0 && status_last != expect_status) {
    fprintf(stderr, "FAIL final status %03x wanted %03x\n", status_last, expect_status);
    failed = 1;
  }
  if (!failed && !expect_seq.empty()) {
    if (status_seq.size() != expect_seq.size()) {
      fprintf(stderr, "FAIL status sequence length %zu wanted %zu\n",
              status_seq.size(), expect_seq.size());
      failed = 1;
    } else {
      for (size_t i = 0; i < expect_seq.size(); i++) {
        if (status_seq[i] != expect_seq[i]) {
          fprintf(stderr, "FAIL status seq[%zu] %03x wanted %03x\n",
                  i, status_seq[i], expect_seq[i]);
          failed = 1;
          break;
        }
      }
    }
  }

  if (exhaust_rises) {
    int led_now = top->led ? 1 : 0;
    if (!halt_at || led_now || rises != exhaust_rises) {
      fprintf(stderr, "FAIL exhaust rises %d led %d halt %llu wanted %d\n",
              rises, led_now, (unsigned long long)halt_at, exhaust_rises);
      failed = 1;
    } else if ((uint64_t)top->mask != 0xffffffffffULL || top->r5 != 0 || top->r9 != 0) {
      fprintf(stderr, "FAIL mask/r5/r9 at the halt\n");
      failed = 1;
    }
  } else if (expect_halt) {
    if (!halt_at || saw_led) {
      fprintf(stderr, "FAIL expected a dark halt\n");
      failed = 1;
    }
    if (expect_no_arm && saw_arm) {
      fprintf(stderr, "FAIL arm word was stored\n");
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
      uint64_t want = 0;
      for (size_t i = 1; i < edges.size(); i++) {
        uint64_t expect = (period2 && (int)i > switch_after) ? period2 : period;
        uint64_t d = edges[i] - edges[i - 1];
        uint64_t diff = d > expect ? d - expect : expect - d;
        acc += d;
        want += expect;
        if (diff > slack) {
          fprintf(stderr, "FAIL period %llu wanted %llu slack %llu gap %zu\n",
                  (unsigned long long)d, (unsigned long long)expect,
                  (unsigned long long)slack, i);
          failed = 1;
          break;
        }
      }
      if (!failed) {
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
    }
  }
  // Button held across three edges. The LED stays at the level the
  // first edge reached (on), then the same period resumes.
  if (press && !failed && !expect_halt && !exhaust_rises) {
    if (hold_cycles == 0) hold_cycles = period * 3;
    if (edges.size() != 1 || !top->led || hold_cycles == 0) {
      fprintf(stderr, "FAIL press wants one rising edge and a hold\n");
      failed = 1;
    } else {
      int held_led = top->led ? 1 : 0;
      // The edge break leaves prev at the level before the edge.
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
      top->btn_n = 0;
      printf("PRESS cycle %llu led %d hold %llu\n",
             (unsigned long long)cycle, held_led,
             (unsigned long long)hold_cycles);
      for (uint64_t n = 0; n < hold_cycles; n++) {
        cycle++;
        step();
        if (top->mem_write && fell_through(top->mem_addr)) {
          fprintf(stderr, "FAIL store to %08x during hold\n", (unsigned)top->mem_addr);
          failed = 1;
          break;
        }
        int screen = top->screen_we ? 1 : 0;
        if (screen && !prev_screen) screen_during++;
        prev_screen = screen;
        int led = top->led ? 1 : 0;
        if (led != prev) edges_during++;
        if (led != held_led) {
          fprintf(stderr, "FAIL led changed during hold at %llu\n",
                  (unsigned long long)cycle);
          failed = 1;
          break;
        }
        prev = led;
      }
      printf("HOLD edges %d screen %d led %d\n", edges_during, screen_during, held_led);
      if (edges_during || screen_during) {
        fprintf(stderr, "FAIL blink advanced while the button was held\n");
        failed = 1;
      }
      top->btn_n = 1;
      uint64_t released = cycle;
      printf("RELEASE cycle %llu\n", (unsigned long long)released);
      std::vector<uint64_t> resume;
      uint64_t limit = released + period + slack + period + slack + 4096;
      while (!failed && resume.size() < 2 && cycle < limit) {
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
  top->final();
  delete top;
  return failed;
}
