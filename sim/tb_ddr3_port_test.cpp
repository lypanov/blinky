#include "Vddr3_port_test_top.h"
#include "verilated.h"

#include <cstdio>
#include <cstdlib>
#include <string>

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  Vddr3_port_test_top top;
  top.clk = 0;
  top.rst_n = 0;
  for (int i = 0; i < 4; i++) {
    top.clk = !top.clk;
    top.eval();
  }
  top.rst_n = 1;
  bool done = false;
  for (int i = 0; i < 200000 && !done; i++) {
    top.clk = !top.clk;
    top.eval();
    if (top.clk && top.done)
      done = true;
  }
  std::printf("done=%d passed=%d failed=%d edge=%d\n",
              top.done, top.passed, top.failed, top.edge_sel);
  bool corrupt = false;
  bool late = false;
  for (int i = 1; i < argc; i++) {
    if (std::string(argv[i]) == "+ddr3_corrupt")
      corrupt = true;
    if (std::string(argv[i]) == "+ddr3_late")
      late = true;
  }
  if (!done) {
    std::printf("TIMEOUT\n");
    return 1;
  }
  if (corrupt) {
    if (top.passed || !top.failed) {
      std::printf("corrupt model lit a pass\n");
      return 1;
    }
    return 0;
  }
  if (!top.passed || top.failed) {
    std::printf("good model did not pass\n");
    return 1;
  }
  int expect_edge = late ? 1 : 0;
  if (top.edge_sel != expect_edge) {
    std::printf("locked edge %d, expected %d\n", top.edge_sel, expect_edge);
    return 1;
  }
  return 0;
}
