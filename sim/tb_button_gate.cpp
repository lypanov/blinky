// Button and UART press set one level. The LED pin is not in this
// module: Blink reads the level and decides. One binary, two clocks:
// --div 117 is the Nano 4K, --div 210 is the Dock.
#include "Vbutton_gate.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  int div = 0;
  const char* name = "gate";
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--div") && i + 1 < argc) div = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--name") && i + 1 < argc) name = argv[++i];
  }
  if (div < 8) {
    fprintf(stderr, "need --div 117 or 210\n");
    return 2;
  }

  auto* top = new Vbutton_gate;
  int cycle = 0;
  top->clk = 0;
  top->resetn = 0;
  top->btn_n = 1;
  top->uart_rx = 1;
  top->eval();

  std::vector<int> s;
  auto tick = [&]() {
    top->clk = 0;
    top->eval();
    top->clk = 1;
    top->eval();
    s.push_back(top->pressed ? 1 : 0);
    cycle++;
  };

  for (int i = 0; i < 8; i++) tick();
  top->resetn = 1;

  for (int i = 0; i < 400; i++) tick();

  // Active-low button. Down is inclusive, up is exclusive, counted
  // from the tick that first samples the new level.
  int down = cycle;
  top->btn_n = 0;
  for (int i = 0; i < 800; i++) tick();
  int up = cycle;
  top->btn_n = 1;
  for (int i = 0; i < 400; i++) tick();

  auto send = [&](uint8_t byte) {
    int start = cycle;
    top->uart_rx = 0;
    for (int i = 0; i < div; i++) tick();
    for (int bit = 0; bit < 8; bit++) {
      top->uart_rx = (byte >> bit) & 1;
      for (int i = 0; i < div; i++) tick();
    }
    top->uart_rx = 1;
    for (int i = 0; i < div; i++) tick();
    for (int i = 0; i < div; i++) tick();
    return start;
  };

  int bad = send(0x55);
  for (int i = 0; i < 200; i++) tick();
  int press = send(0x01);
  for (int i = 0; i < 400; i++) tick();
  int release = send(0x00);
  for (int i = 0; i < 400; i++) tick();
  send(0x31);
  for (int i = 0; i < 200; i++) tick();
  // Button held across a UART release. The level stays pressed.
  int both = cycle;
  top->btn_n = 0;
  for (int i = 0; i < 20; i++) tick();
  send(0x30);
  for (int i = 0; i < 80; i++) tick();
  int both_up = cycle;
  top->btn_n = 1;
  for (int i = 0; i < 400; i++) tick();
  send(0x20);
  for (int i = 0; i < 200; i++) tick();
  send(0x00);
  for (int i = 0; i < 400; i++) tick();

  int fails = 0;
  auto fail = [&](const char* msg, int c) {
    if (fails < 12)
      fprintf(stderr, "FAIL %s %s at %d pressed=%d\n", name, msg, c, s[c]);
    fails++;
  };

  for (int c = 12; c < down; c++) {
    if (s[c]) fail("idle", c);
  }

  // Two flops. The sample at `down` takes btn0 low. The next takes
  // btn1 low, which is the pressed level seen after that tick.
  if (down + 2 >= (int)s.size()) return 2;
  for (int c = down + 2; c < up + 1; c++) {
    if (!s[c]) fail("button", c);
  }
  for (int c = up + 2; c < bad; c++) {
    if (s[c]) fail("button-release", c);
  }

  auto wait_pressed = [&](int from, int want, const char* msg) -> int {
    int limit = from + div * 14;
    if (limit > (int)s.size()) limit = (int)s.size();
    for (int c = from; c < limit; c++) {
      if (s[c] == want) return c;
    }
    fprintf(stderr, "FAIL %s %s never became %d after %d\n", name, msg, want, from);
    fails++;
    return from;
  };

  int bad_at = wait_pressed(bad, 0, "ignored");
  for (int c = bad_at; c < press; c++) {
    if (s[c]) fail("ignored", c);
  }

  int on = wait_pressed(press, 1, "press01");
  int off = wait_pressed(release, 0, "release00");
  for (int c = on; c < release; c++) {
    if (!s[c]) fail("uart01", c);
  }
  for (int c = off; c < off + 300 && c < (int)s.size(); c++) {
    if (s[c]) fail("after00", c);
  }

  // '1' latches. Button stays down across '0', so the level stays
  // pressed until the button itself rises.
  int on1 = wait_pressed(off + 300, 1, "press31");
  (void)on1;
  for (int c = both + 2; c < both_up + 1; c++) {
    if (!s[c]) fail("button-over-uart-release", c);
  }
  int off0 = wait_pressed(both_up, 0, "button-up-after-0");
  for (int c = off0; c < off0 + 200 && c < (int)s.size(); c++) {
    if (s[c]) fail("after-button", c);
  }

  int onsp = wait_pressed(off0 + 200, 1, "space");
  for (int c = onsp; c < onsp + 100 && c < (int)s.size(); c++) {
    if (!s[c]) fail("space-hold", c);
  }
  int offsp = wait_pressed(onsp + 100, 0, "space-release");
  for (int c = offsp; c < (int)s.size(); c++) {
    if (s[c]) fail("final", c);
  }

  if (fails) {
    fprintf(stderr, "FAIL %s %d\n", name, fails);
    return 1;
  }
  printf("ok %s div=%d button %d..%d uart01_at=%d release_at=%d\n",
         name, div, down, up, on, off);
  return 0;
}
