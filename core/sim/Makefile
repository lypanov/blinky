# Blink2 Verilator simulation (CPUSubset0 + mock RAM).
# Generate Verilog with Mill (from repo root), then build/run the C++ testbench.
#
# Usage (from repo root):
#   make -C core/sim sim
# or:
#   tools/run_verilator_sim.sh

CORE      := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
REPO      := $(abspath $(CORE)/..)
SIMDIR    := $(CORE)/sim
OUT       := $(SIMDIR)/out
GEN       := $(REPO)/generated
TOP       := CPUSimTop
VSRC      := $(GEN)/$(TOP).v
TB        := $(SIMDIR)/tb_blink2.cpp
OBJDIR    := $(SIMDIR)/obj_dir
BIN       := $(OBJDIR)/cpu_sim
VERILATOR ?= verilator
CYCLES    ?= 800
TOGGLES   ?= 6

export PATH := $(HOME)/bin:/usr/local/bin:$(PATH)
export CHISEL_CPU_PROJECT_ROOT := $(CORE)

.PHONY: all sim verilate run wave plot visualizer clean generate

all: sim

generate: $(VSRC)

$(VSRC): $(CORE)/src/main/scala/gcd/CPUSimTop.scala $(CORE)/src/main/scala/gcd/CPUSubset0.scala $(CORE)/tests/Blink2test.code
	@mkdir -p $(GEN)
	cd $(REPO) && mill chisel-blinky.runMain gcd.CPUSimTop

$(BIN): $(VSRC) $(TB)
	@mkdir -p $(OUT)
	$(VERILATOR) --cc --exe --build --trace-fst \
		--top-module $(TOP) \
		--Mdir $(OBJDIR) \
		--timescale 1ns/1ps \
		-DPRINTF_COND=0 \
		-Wno-fatal \
		-Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND \
		-Wno-UNUSED -Wno-UNDRIVEN -Wno-PINMISSING \
		-CFLAGS "-std=c++17 -O2" \
		-o cpu_sim \
		$(VSRC) $(TB)

verilate: $(BIN)

run: $(BIN)
	@mkdir -p $(OUT)
	cd $(REPO) && $(BIN) \
		--cycles $(CYCLES) \
		--toggles $(TOGGLES) \
		--fst $(OUT)/blink2.fst \
		--led $(OUT)/led_toggles.csv \
		--trace $(OUT)/blink2_trace.json
	python3 $(SIMDIR)/annotate_trace.py \
		--trace $(OUT)/blink2_trace.json \
		--wave $(OUT)/led_wave.csv \
		--program $(OUT)/program.json \
		--out $(OUT)/blink2_trace.json \
		--visualizer $(SIMDIR)/visualizer/trace.json

plot: run
	python3 $(SIMDIR)/plot_led.py \
		--csv $(OUT)/led_wave.csv \
		--toggles $(OUT)/led_toggles.csv \
		--png $(OUT)/led_waveform.png
	@echo "Waveform PNG: $(OUT)/led_waveform.png"
	@echo "FST (GTKWave): $(OUT)/blink2.fst"

sim: plot
	@echo ""
	@echo "Phase 1 simulation complete."
	@echo "  FST:  $(OUT)/blink2.fst"
	@echo "  PNG:  $(OUT)/led_waveform.png"
	@echo "  LED:  $(OUT)/led_toggles.csv"
	@echo "Open in GTKWave:"
	@echo "  gtkwave $(OUT)/blink2.fst $(SIMDIR)/gtkwave_led.gtkw"

wave: run
	gtkwave -S $(SIMDIR)/gtkwave_led.tcl $(OUT)/blink2.fst $(SIMDIR)/gtkwave_led.gtkw

visualizer: sim
	python3 $(SIMDIR)/visualizer/serve.py

clean:
	rm -rf $(OBJDIR) $(OUT) $(GEN)/CPUSimTop.v $(GEN)/CPUSimTop.sv
	rm -f $(SIMDIR)/visualizer/trace.json $(SIMDIR)/visualizer/program.json
