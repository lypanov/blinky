// Button or UART press forces the LED pin off. The cpu_led input keeps
// toggling, and a release makes the pin follow it on that same cycle.
// One binary, two clocks: --div 117 is the Nano 4K, --div 210 is the Dock.
#include "Vbutton_gate.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static const int PERIOD = 40;

struct Sample {
  int led;
  int cpu;
  int pressed;
};

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
  top->cpu_led = 0;
  top->btn_n = 1;
  top->uart_rx = 1;
  top->eval();

  std::vector<Sample> s;
  auto tick = [&]() {
    top->cpu_led = ((cycle / PERIOD) & 1);
    top->clk = 0;
    top->eval();
    top->clk = 1;
    top->eval();
    s.push_back({(int)top->led, (int)top->cpu_led, (int)top->pressed});
    cycle++;
  };

  for (int i = 0; i < 8; i++) tick();
  top->resetn = 1;

  // Idle. The pin follows cpu_led.
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
    // A few extra bits of idle so the stop sample lands.
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
  // Button held across a UART release. The pin stays off.
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
      fprintf(stderr, "FAIL %s %s at %d led=%d cpu=%d pressed=%d\n",
              name, msg, c, s[c].led, s[c].cpu, s[c].pressed);
    fails++;
  };

  // Reset held the latch clear. From a few cycles after resetn, until
  // the button, the pin matches the CPU register.
  for (int c = 12; c < down; c++) {
    if (s[c].pressed || s[c].led != s[c].cpu) fail("idle", c);
  }

  // Two flops. The sample at `down` takes btn0 low. The next takes
  // btn1 low, which is the pressed level seen after that tick.
  if (down + 2 >= (int)s.size()) return 2;
  for (int c = down + 2; c < up + 1; c++) {
    if (!s[c].pressed || s[c].led) fail("button", c);
  }
  int cpu_edges = 0;
  for (int c = down + 2; c < up + 1; c++) {
    if (s[c].cpu != s[c - 1].cpu) cpu_edges++;
  }
  if (cpu_edges < 10) {
    fprintf(stderr, "FAIL %s button window saw %d cpu edges\n", name, cpu_edges);
    fails++;
  }
  // Release: btn1 goes high on the tick after `up`.
  for (int c = up + 2; c < bad; c++) {
    if (s[c].pressed || s[c].led != s[c].cpu) fail("button-release", c);
  }

  auto wait_pressed = [&](int from, int want, const char* msg) -> int {
    int limit = from + div * 14;
    if (limit > (int)s.size()) limit = (int)s.size();
    for (int c = from; c < limit; c++) {
      if (s[c].pressed == want) return c;
    }
    fprintf(stderr, "FAIL %s %s never became %d after %d\n", name, msg, want, from);
    fails++;
    return from;
  };

  int bad_at = wait_pressed(bad, 0, "ignored");
  for (int c = bad_at; c < press; c++) {
    if (s[c].pressed || s[c].led != s[c].cpu) fail("ignored", c);
  }

  auto hold_off = [&](int from, int until, const char* msg) {
    int saw0 = 0, saw1 = 0;
    for (int c = from; c < until; c++) {
      if (!s[c].pressed || s[c].led) fail(msg, c);
      if (s[c].cpu) saw1 = 1;
      else saw0 = 1;
    }
    if (!saw0 || !saw1) {
      fprintf(stderr, "FAIL %s %s cpu did not toggle (%d/%d)\n", name, msg, saw0, saw1);
      fails++;
    }
  };
  auto hold_follow = [&](int from, int until, const char* msg) {
    int edges = 0;
    for (int c = from; c < until; c++) {
      if (s[c].pressed || s[c].led != s[c].cpu) fail(msg, c);
      if (c > from && s[c].cpu != s[c - 1].cpu) edges++;
    }
    if (edges < 4) {
      fprintf(stderr, "FAIL %s %s only %d cpu edges\n", name, msg, edges);
      fails++;
    }
  };

  int on = wait_pressed(press, 1, "press01");
  int off = wait_pressed(release, 0, "release00");
  hold_off(on, release, "uart01");
  hold_follow(off, off + 300, "after00");

  // '1' latches. Button stays down across '0', so the pin stays off
  // until the button itself rises.
  int on1 = wait_pressed(off + 300, 1, "press31");
  (void)on1;
  for (int c = both + 2; c < both_up + 1; c++) {
    if (!s[c].pressed || s[c].led) fail("button-over-uart-release", c);
  }
  int off0 = wait_pressed(both_up, 0, "button-up-after-0");
  hold_follow(off0, off0 + 200, "after-button");

  int onsp = wait_pressed(off0 + 200, 1, "space");
  hold_off(onsp, onsp + 100, "space-hold");
  int offsp = wait_pressed(onsp + 100, 0, "space-release");
  hold_follow(offsp, (int)s.size() - 1, "final");

  // The CPU edges while the pin was forced off stayed one PERIOD apart.
  int prev = -1;
  int bad_gap = 0;
  for (int c = down + 2; c < up + 1; c++) {
    if (s[c].cpu != s[c - 1].cpu) {
      if (prev >= 0 && c - prev != PERIOD) bad_gap++;
      prev = c;
    }
  }
  if (prev < 0 || bad_gap) {
    fprintf(stderr, "FAIL %s cpu period while held\n", name);
    fails++;
  }

  if (fails) {
    fprintf(stderr, "FAIL %s %d\n", name, fails);
    return 1;
  }
  printf("ok %s div=%d button %d..%d cpu_edges=%d uart01_at=%d release_at=%d\n",
         name, div, down, up, cpu_edges, on, off);
  return 0;
}
