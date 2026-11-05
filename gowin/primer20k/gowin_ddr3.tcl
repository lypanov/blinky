# Primer 20K Dock DDR3 data port. Device GW2A-LV18PG256C8/I7.
# Invoked from tools/gowin_build.sh FPGA_IMAGE=ddr3 BOARD=primer20k.
# SRAM-loadable .fs only. Do not flash.

set HERE [file dirname [info script]]
set ROOT [file normalize [file join $HERE ../..]]
set GOWIN [file join $ROOT gowin]

set_device -name GW2A-18C GW2A-LV18PG256C8/I7

add_file -type verilog [file join $GOWIN src CPUMinimalWrapper.v]
add_file -type verilog [file join $ROOT generated InstrRom.v]
add_file -type verilog [file join $HERE blinky_top_ddr3.v]
add_file -type verilog [file join $HERE ddr3_pll.v]
add_file -type verilog [file join $HERE ddr3 gowin_clkdiv.v]
add_file -type verilog [file join $HERE ddr3 ddr3_controller.v]
add_file -type verilog [file join $HERE ddr3_port_test.v]
add_file -type verilog [file join $GOWIN ip gowin_sp.v]
add_file -type cst     [file join $HERE ddr3.cst]
add_file -type sdc     [file join $HERE ddr3.sdc]

set_option -top_module blinky_top_ddr3
set_option -verilog_std sysv2017
if {[info exists ::env(GOWIN_OUT_NAME)] && $::env(GOWIN_OUT_NAME) ne ""} {
  set_option -output_base_name $::env(GOWIN_OUT_NAME)
} else {
  set_option -output_base_name ddr3
}
set_option -synthesis_tool gowinsynthesis
set_option -place_option 2
set_option -use_done_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 0
set_option -use_jtag_as_gpio 0

run all
