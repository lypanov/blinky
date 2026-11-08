# Primer 20K Dock DDR3 data port. Device GW2A-LV18PG256C8/I7.
# Invoked from tools/gowin_build.sh FPGA_IMAGE=ddr3 BOARD=primer20k.
# SRAM-loadable .fs only. Do not flash.

set HERE [file dirname [info script]]
set ROOT [file normalize [file join $HERE ../..]]
set GOWIN [file join $ROOT gowin]

set_device -name GW2A-18C GW2A-LV18PG256C8/I7

add_file -type verilog [file join $GOWIN src CPUMinimalWrapper.v]
add_file -type verilog [file join $ROOT generated InstrRom.v]
if {[info exists ::env(SECTOR_ROM)] && $::env(SECTOR_ROM) ne ""} {
  add_file -type verilog $::env(SECTOR_ROM)
}
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
# ddr3_eye.vh is written by tools/gowin_build.sh. The reader image
# defines DDR3_READER. The stored-BL image defines DDR3_FETCH. The
# P/D image defines DDR3_PD. The ModDesc image defines DDR3_MODDESC.
# The Files image defines DDR3_FILES. The Modules image defines
# DDR3_MODULES. The prologue and the ALU do not.
set_option -include_path $HERE
if {[info exists ::env(GOWIN_OUT_NAME)] && $::env(GOWIN_OUT_NAME) ne ""} {
  set_option -output_base_name $::env(GOWIN_OUT_NAME)
} else {
  set_option -output_base_name ddr3
}
set_option -synthesis_tool gowinsynthesis
# place_option 2 on the 2-port register file trains the write eye to
# G=FF00 (F=EB) and the CPU holds at 0x1D8C. route_option 1 on that
# placement holds at 0x1D90 with the same G. place_option 0 with
# route_option 2 trains the pre-arm netlist to G=A55A (F=AB).
# The arm-word netlist is the other way around. route_option 2 leaves
# a one-tap eye (best pop 16, CPU held at 0x0080, F=4B). route_option 1
# trains that netlist to G=A55A (F=AB) and runs the placed loop.
# DDR3_ROUTE_OPTION selects it; other images stay on route_option 2.
set_option -place_option 0
if {[info exists ::env(DDR3_ROUTE_OPTION)] && $::env(DDR3_ROUTE_OPTION) ne ""} {
  set_option -route_option $::env(DDR3_ROUTE_OPTION)
} else {
  set_option -route_option 2
}
set_option -use_done_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 0
set_option -use_jtag_as_gpio 0

run all
