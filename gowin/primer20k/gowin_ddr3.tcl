# Primer 20K Dock DDR3 data port. Device GW2A-LV18PG256C8/I7.
# Invoked from tools/gowin_build.sh FPGA_IMAGE=ddr3 BOARD=primer20k.
# SRAM-loadable .fs only. Do not flash.

set HERE [file dirname [info script]]
set ROOT [file normalize [file join $HERE ../..]]
set GOWIN [file join $ROOT gowin]

set_device -name GW2A-18C GW2A-LV18PG256C8/I7

add_file -type verilog [file join $GOWIN src CPUMinimalWrapper.v]
add_file -type verilog [file join $ROOT generated InstrRom.v]
add_file -type verilog [file join $ROOT generated HwMul.v]
if {[info exists ::env(SECTOR_ROM)] && $::env(SECTOR_ROM) ne ""} {
  add_file -type verilog $::env(SECTOR_ROM)
}
add_file -type verilog [file join $HERE blinky_top_ddr3.v]
add_file -type verilog [file join $GOWIN button_gate.v]
add_file -type verilog [file join $GOWIN uart_word_rx.v]
add_file -type verilog [file join $HERE ddr3_pll.v]
add_file -type verilog [file join $HERE ddr3 gowin_clkdiv.v]
add_file -type verilog [file join $HERE ddr3 ddr3_controller.v]
add_file -type verilog [file join $HERE ddr3_port_test.v]
add_file -type verilog [file join $GOWIN ip gowin_sp.v]
add_file -type sdc     [file join $HERE ddr3.sdc]

# off, flash, square, or text. Text includes the square. The modules
# image defaults to text in tools/gowin_build.sh.
set vmode "off"
if {[info exists ::env(VIDEO_MODE)] && $::env(VIDEO_MODE) ne ""} {
  set vmode $::env(VIDEO_MODE)
}
if {$vmode ne "off" && $vmode ne "flash" && $vmode ne "square" && $vmode ne "text"} {
  puts stderr "error: VIDEO_MODE=$vmode"
  exit 1
}
set vh [open [file join $HERE video_mode.vh] w]
if {$vmode eq "flash" || $vmode eq "square" || $vmode eq "text"} {
  puts $vh "`ifndef VIDEO_MODE_INCLUDED"
  puts $vh "`define VIDEO_MODE_INCLUDED"
  puts $vh "`define VIDEO_ON"
  puts $vh "`define VIDEO_DOCK"
  if {$vmode eq "square" || $vmode eq "text"} {
    puts $vh "`define VIDEO_SQUARE"
  }
  if {$vmode eq "text"} {
    puts $vh "`define VIDEO_TEXT"
  }
  puts $vh "`endif"
  add_file -type verilog [file join $GOWIN video.v]
  add_file -type verilog [file join $GOWIN KeepBit.v]
  # A second add_file cst replaces the first. One file has to carry
  # the DDR3 balls and the HDMI balls.
  set combo [file join $HERE ddr3_hdmi.cst]
  set in [open [file join $HERE ddr3.cst] r]
  set body [read $in]
  close $in
  set in [open [file join $HERE hdmi.cst] r]
  append body "\n" [read $in]
  close $in
  set out [open $combo w]
  puts -nonewline $out $body
  close $out
  add_file -type cst $combo
} else {
  add_file -type cst [file join $HERE ddr3.cst]
  puts $vh "`ifndef VIDEO_MODE_INCLUDED"
  puts $vh "`define VIDEO_MODE_INCLUDED"
  puts $vh "// VIDEO_MODE=off"
  puts $vh "`endif"
}
close $vh

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
# The arm-word 2-port netlist is the other way around. route_option 2
# leaves a one-tap eye (best pop 16, CPU held at 0x0080, F=4B).
# route_option 1 trains that netlist to G=A55A (F=AB) and runs the
# placed loop. The 1-port register-file netlist flips again:
# route_option 1 holds at 0x0080 with F=4B and a dark LED, and
# route_option 2 runs the placed loop. DDR3_ROUTE_OPTION selects it;
# other images stay on route_option 2.
# place_option 0 is the modules default. DDR3_PLACE_OPTION overrides
# it for one image; other images stay on 0.
# The status-register netlist fails the write eye at route_option 2
# (PC 0080, E0 FFFF, F 48). route_option 1 trains it: lanes 000C 000A,
# E0 A55A, G A55A, F A8. DDR3_ROUTE_OPTION still overrides one image.
if {[info exists ::env(DDR3_PLACE_OPTION)] && $::env(DDR3_PLACE_OPTION) ne ""} {
  set_option -place_option $::env(DDR3_PLACE_OPTION)
} else {
  set_option -place_option 0
}
if {[info exists ::env(DDR3_ROUTE_OPTION)] && $::env(DDR3_ROUTE_OPTION) ne ""} {
  set_option -route_option $::env(DDR3_ROUTE_OPTION)
} else {
  set_option -route_option 1
}
set_option -use_done_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 0
set_option -use_jtag_as_gpio 0
# Post-place file names the MULT36X36 site. Placement is unchanged.
set_option -gen_posp 1

run all
