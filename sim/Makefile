# Retired Blink2 / Blink3 Verilator targets. The current proof is
# sim/run_disk_boot.sh and sim/run_uart_disk.sh, via tools/run_verilator_sim.sh.
#
# Usage (from repo root):
#   tools/run_verilator_sim.sh

ROOT      := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
SIMDIR    := $(ROOT)/sim
OUT       := $(SIMDIR)/out
GEN       := $(ROOT)/generated
TB        := $(SIMDIR)/tb_blink2.cpp
VERILATOR ?= verilator
CYCLES    ?= 800
TOGGLES   ?= 6
BLINK3_CYCLES ?= 800

export PATH := $(HOME)/bin:/usr/local/bin:$(PATH)
export CHISEL_CPU_PROJECT_ROOT := $(ROOT)

VERILATOR_FLAGS := --cc --exe --build --trace-fst \
	--top-module CPUSimTop \
	--timescale 1ns/1ps \
	-DPRINTF_COND=0 \
	-Wno-fatal \
	-Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND \
	-Wno-UNUSED -Wno-UNDRIVEN -Wno-PINMISSING \
	-CFLAGS "-std=c++17 -O2"

.PHONY: all sim verilate run wave plot visualizer clean generate traces \
	imem-blink3 generate-blink2 generate-blink3 \
	verilate-blink2 verilate-blink3 run-blink2 run-blink3

all: traces

# --- Blink3 IMEM (unfixed final_system.code + trampoline) ---
IMEM3 := $(SIMDIR)/visualizer/imem/blink3.words

imem-blink3: $(IMEM3)

$(IMEM3): $(ROOT)/tests/final_system.code $(SIMDIR)/build_blink3_imem.py $(SIMDIR)/imem_layout.py
	python3 $(SIMDIR)/build_blink3_imem.py

# --- Verilog ---
generate: generate-blink2

generate-blink2: $(GEN)/CPUSimTop.v

$(GEN)/CPUSimTop.v: $(ROOT)/src/main/scala/gcd/CPUSimTop.scala $(ROOT)/src/main/scala/gcd/CPUSubset0.scala $(ROOT)/tests/Blink2test.code
	@mkdir -p $(GEN)
	cd $(ROOT) && SIM_IMAGE=blink2 mill chisel-blinky.runMain gcd.CPUSimTop

generate-blink3: $(GEN)/CPUSimTopBlink3.v

$(GEN)/CPUSimTopBlink3.v: $(ROOT)/src/main/scala/gcd/CPUSimTop.scala $(ROOT)/src/main/scala/gcd/CPUSubset0.scala $(IMEM3)
	@mkdir -p $(GEN)
	cd $(ROOT) && SIM_IMAGE=blink3 mill chisel-blinky.runMain gcd.CPUSimTop

# --- Verilate ---
BIN2 := $(SIMDIR)/obj_dir_blink2/cpu_sim
BIN3 := $(SIMDIR)/obj_dir_blink3/cpu_sim

verilate-blink2: $(BIN2)
verilate-blink3: $(BIN3)

$(BIN2): $(GEN)/CPUSimTop.v $(GEN)/InstrRom.v $(TB)
	@mkdir -p $(OUT)
	$(VERILATOR) $(VERILATOR_FLAGS) \
		--Mdir $(SIMDIR)/obj_dir_blink2 \
		-o cpu_sim \
		$(GEN)/CPUSimTop.v $(GEN)/InstrRom.v $(TB)

$(BIN3): $(GEN)/CPUSimTopBlink3.v $(GEN)/InstrRom.v $(TB)
	@mkdir -p $(OUT)
	$(VERILATOR) $(VERILATOR_FLAGS) \
		--Mdir $(SIMDIR)/obj_dir_blink3 \
		-o cpu_sim \
		$(GEN)/CPUSimTopBlink3.v $(GEN)/InstrRom.v $(TB)

verilate: verilate-blink2

# --- Run + annotate ---
TRACE_DIR := $(SIMDIR)/visualizer/traces

run-blink2: $(BIN2)
	@mkdir -p $(OUT) $(TRACE_DIR)
	cd $(ROOT) && $(BIN2) \
		--program blink2 \
		--cycles $(CYCLES) \
		--toggles $(TOGGLES) \
		--fst $(OUT)/blink2.fst \
		--led $(OUT)/led_toggles.csv \
		--trace $(OUT)/blink2_trace.json
	python3 $(SIMDIR)/annotate_trace.py \
		--image blink2 \
		--trace $(OUT)/blink2_trace.json \
		--wave $(OUT)/led_wave.csv \
		--program $(OUT)/program_blink2.json \
		--out $(OUT)/blink2_trace.json \
		--visualizer $(TRACE_DIR)/blink2.json
	cp -f $(OUT)/program_blink2.json $(TRACE_DIR)/blink2_program.json

run-blink3: $(BIN3)
	@mkdir -p $(OUT) $(TRACE_DIR)
	cd $(ROOT) && $(BIN3) \
		--program blink3 \
		--cycles $(BLINK3_CYCLES) \
		--toggles 0 \
		--fst $(OUT)/blink3.fst \
		--led $(OUT)/blink3_led_toggles.csv \
		--trace $(OUT)/blink3_trace.json
	python3 $(SIMDIR)/annotate_trace.py \
		--image blink3 \
		--imem $(IMEM3) \
		--trace $(OUT)/blink3_trace.json \
		--wave $(OUT)/blink3_led_wave.csv \
		--program $(OUT)/program_blink3.json \
		--out $(OUT)/blink3_trace.json \
		--visualizer $(TRACE_DIR)/blink3.json
	cp -f $(OUT)/program_blink3.json $(TRACE_DIR)/blink3_program.json

traces: run-blink2 run-blink3
	@echo ""
	@echo "Visualizer traces:"
	@echo "  $(TRACE_DIR)/blink2.json"
	@echo "  $(TRACE_DIR)/blink3.json"

# Legacy Phase 1 aliases (Blink2).
run: run-blink2
plot: run-blink2
	python3 $(SIMDIR)/plot_led.py \
		--csv $(OUT)/led_wave.csv \
		--toggles $(OUT)/led_toggles.csv \
		--png $(OUT)/led_waveform.png
	@echo "Waveform PNG: $(OUT)/led_waveform.png"

sim:
	@echo "the Blink2 sim is retired; run tools/run_verilator_sim.sh" >&2
	@exit 1

wave: run-blink2
	gtkwave -S $(SIMDIR)/gtkwave_led.tcl $(OUT)/blink2.fst $(SIMDIR)/gtkwave_led.gtkw

visualizer: traces
	python3 $(SIMDIR)/visualizer/serve.py

clean:
	rm -rf $(SIMDIR)/obj_dir $(SIMDIR)/obj_dir_blink2 $(SIMDIR)/obj_dir_blink3 \
		$(OUT) $(GEN)/CPUSimTop.v $(GEN)/CPUSimTopBlink3.v $(GEN)/CPUSimTop.sv
	rm -f $(SIMDIR)/visualizer/trace.json $(SIMDIR)/visualizer/program.json
