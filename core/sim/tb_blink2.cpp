// Verilator testbench for Blink2 on CPUSimTop (CPUSubset0 + mock RAM).
// Drives clock/reset, dumps an FST waveform, logs LED toggles, and writes a
// cycle-accurate JSON trace for the visualizer.

#include "VCPUSimTop.h"
#include "VCPUSimTop___024root.h"
#include "verilated.h"
#include "verilated_fst_c.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

static uint32_t cpu_reg(VCPUSimTop* top, int i) {
  auto* r = top->rootp;
  switch (i) {
    case 0: return r->CPUSimTop__DOT__cpu__DOT__regs_0;
    case 1: return r->CPUSimTop__DOT__cpu__DOT__regs_1;
    case 2: return r->CPUSimTop__DOT__cpu__DOT__regs_2;
    case 3: return r->CPUSimTop__DOT__cpu__DOT__regs_3;
    case 4: return r->CPUSimTop__DOT__cpu__DOT__regs_4;
    case 5: return r->CPUSimTop__DOT__cpu__DOT__regs_5;
    case 6: return r->CPUSimTop__DOT__cpu__DOT__regs_6;
    case 7: return r->CPUSimTop__DOT__cpu__DOT__regs_7;
    case 8: return r->CPUSimTop__DOT__cpu__DOT__regs_8;
    case 9: return r->CPUSimTop__DOT__cpu__DOT__regs_9;
    case 10: return r->CPUSimTop__DOT__cpu__DOT__regs_10;
    case 11: return r->CPUSimTop__DOT__cpu__DOT__regs_11;
    case 12: return r->CPUSimTop__DOT__cpu__DOT__regs_12;
    case 13: return r->CPUSimTop__DOT__cpu__DOT__regs_13;
    case 14: return r->CPUSimTop__DOT__cpu__DOT__regs_14;
    case 15: return r->CPUSimTop__DOT__cpu__DOT__regs_15;
    default: return 0;
  }
}

static vluint64_t main_time = 0;
double sc_time_stamp() { return static_cast<double>(main_time); }

struct Options {
  int max_cycles = 800;
  int reset_cycles = 4;
  int min_toggles = 6;
  std::string fst_path = "sim/out/blink2.fst";
  std::string led_path = "sim/out/led_toggles.csv";
  std::string trace_path = "sim/out/blink2_trace.json";
  std::string wave_csv_path = "sim/out/led_wave.csv";
};

static void usage(const char* argv0) {
  fprintf(stderr,
          "Usage: %s [options]\n"
          "  --cycles N       Max cycles after reset (default 800)\n"
          "  --toggles N      Stop after N LED edges (default 6)\n"
          "  --reset N        Reset cycles (default 4)\n"
          "  --fst PATH       FST waveform output\n"
          "  --trace PATH     JSON cycle trace output\n"
          "  --led PATH       LED toggle CSV output\n",
          argv0);
}

static Options parse_args(int argc, char** argv) {
  Options o;
  for (int i = 1; i < argc; i++) {
    auto need = [&](const char* name) -> const char* {
      if (i + 1 >= argc) {
        fprintf(stderr, "missing value for %s\n", name);
        exit(2);
      }
      return argv[++i];
    };
    if (!strcmp(argv[i], "--cycles")) o.max_cycles = atoi(need("--cycles"));
    else if (!strcmp(argv[i], "--toggles")) o.min_toggles = atoi(need("--toggles"));
    else if (!strcmp(argv[i], "--reset")) o.reset_cycles = atoi(need("--reset"));
    else if (!strcmp(argv[i], "--fst")) o.fst_path = need("--fst");
    else if (!strcmp(argv[i], "--trace")) o.trace_path = need("--trace");
    else if (!strcmp(argv[i], "--led")) o.led_path = need("--led");
    else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
      usage(argv[0]);
      exit(0);
    } else {
      fprintf(stderr, "unknown arg: %s\n", argv[i]);
      usage(argv[0]);
      exit(2);
    }
  }
  return o;
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  Verilated::traceEverOn(true);
  Options opt = parse_args(argc, argv);

  VCPUSimTop* top = new VCPUSimTop;
  VerilatedFstC* tfp = new VerilatedFstC;
  top->trace(tfp, 99);
  tfp->open(opt.fst_path.c_str());

  // 10 ns per half-cycle (20 ns period ≈ 50 MHz) so GTKWave's time axis is readable.
  auto tick = [&]() {
    top->clock = 0;
    top->eval();
    tfp->dump(main_time);
    main_time += 10;
    top->clock = 1;
    top->eval();
    tfp->dump(main_time);
    main_time += 10;
  };

  // Active-high synchronous reset (Chisel default).
  top->reset = 1;
  top->clock = 0;
  top->eval();
  for (int i = 0; i < opt.reset_cycles; i++) tick();
  top->reset = 0;
  tick();  // first cycle out of reset still settling

  std::ofstream led_csv(opt.led_path);
  std::ofstream wave_csv(opt.wave_csv_path);
  std::ofstream trace(opt.trace_path);
  led_csv << "cycle,led_prev,led_next,pc,r0\n";
  wave_csv << "cycle,led,pc,halted,mem_write,mem_addr,mem_wdata,r0,r1,r2,r3\n";
  trace << "{\n  \"program\": \"Blink2test (sim delay maxIterations=5)\",\n";
  trace << "  \"reset_cycles\": " << opt.reset_cycles << ",\n";
  trace << "  \"cycles\": [\n";

  int prev_led = top->io_led ? 1 : 0;
  int toggles = 0;
  std::vector<int> toggle_cycles;
  bool first_json = true;

  int cycle = 0;
  for (; cycle < opt.max_cycles; cycle++) {
    tick();

    const int led = top->io_led ? 1 : 0;
    const uint32_t pc = static_cast<uint32_t>(top->io_pc);
    const uint32_t r0 = static_cast<uint32_t>(top->io_r0);
    const uint32_t r1 = static_cast<uint32_t>(top->io_r1);
    const uint32_t r2 = static_cast<uint32_t>(top->io_r2);
    const uint32_t r3 = static_cast<uint32_t>(top->io_r3);
    const int halted = top->io_halted ? 1 : 0;
    const int mem_wr = top->io_memWrite ? 1 : 0;
    const uint32_t mem_addr = static_cast<uint32_t>(top->io_memAddr);
    const uint32_t mem_wdata = static_cast<uint32_t>(top->io_memWriteData);

    const int nflag = top->rootp->CPUSimTop__DOT__cpu__DOT__n ? 1 : 0;
    const int zflag = top->rootp->CPUSimTop__DOT__cpu__DOT__z ? 1 : 0;

    wave_csv << cycle << "," << led << "," << pc << "," << halted << ","
             << mem_wr << "," << mem_addr << "," << mem_wdata << ","
             << r0 << "," << r1 << "," << r2 << "," << r3 << "\n";

    if (!first_json) trace << ",\n";
    first_json = false;
    trace << "    {\"cycle\":" << cycle
          << ",\"pc\":" << pc
          << ",\"led\":" << led
          << ",\"halted\":" << halted
          << ",\"memWrite\":" << (mem_wr ? "true" : "false")
          << ",\"memAddr\":" << mem_addr
          << ",\"memWriteData\":" << mem_wdata
          << ",\"n\":" << nflag
          << ",\"z\":" << zflag;
    for (int ri = 0; ri < 16; ri++) {
      trace << ",\"r" << ri << "\":" << cpu_reg(top, ri);
    }
    trace << "}";

    if (led != prev_led) {
      toggles++;
      toggle_cycles.push_back(cycle);
      led_csv << cycle << "," << prev_led << "," << led << "," << pc << "," << r0 << "\n";
      printf("[LED] cycle=%d  %d -> %d  pc=0x%08x r0=%u\n",
             cycle, prev_led, led, pc, r0);
      fflush(stdout);
      prev_led = led;
      if (toggles >= opt.min_toggles) {
        cycle++;  // count the cycle we just ran
        break;
      }
    }

    if (halted) {
      printf("[SIM] CPU halted at cycle %d pc=0x%08x\n", cycle, pc);
      cycle++;
      break;
    }
  }

  trace << "\n  ],\n";
  trace << "  \"led_toggles\": [";
  for (size_t i = 0; i < toggle_cycles.size(); i++) {
    if (i) trace << ", ";
    trace << toggle_cycles[i];
  }
  trace << "]\n}\n";

  tfp->close();
  top->final();
  delete tfp;
  delete top;

  printf("[SIM] ran %d cycles after reset, %d LED edges, FST=%s\n",
         cycle, toggles, opt.fst_path.c_str());
  if (toggle_cycles.size() >= 2) {
    printf("[SIM] LED edge cycles:");
    for (int cyc : toggle_cycles) printf(" %d", cyc);
    printf("\n[SIM] periods (cycles between edges):");
    long sum = 0;
    int n = 0;
    for (size_t i = 1; i < toggle_cycles.size(); i++) {
      int p = toggle_cycles[i] - toggle_cycles[i - 1];
      printf(" %d", p);
      sum += p;
      n++;
    }
    printf("\n");
    if (n) {
      printf("[SIM] mean period = %.2f cycles (Treadle Blink2test was ~81-89)\n",
             (double)sum / n);
    }
  } else {
    fprintf(stderr, "[SIM] WARNING: LED did not toggle enough times to measure a period\n");
  }

  return (toggles >= 2) ? 0 : 1;
}
