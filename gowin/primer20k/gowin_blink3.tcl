# Primer 20K Dock Blink3. Device: GW2A-LV18PG256C8/I7 (GW2A-18C).
# Invoked from tools/gowin_build.sh BOARD=primer20k. Do not run with
# QT_QPA_PLATFORM=offscreen (gw_sh crashes). SRAM-loadable .fs only.
# Reuses the same CPUMinimalWrapper.v + Gowin_SP as the Nano 4K; the SP
# primitive is identical on GW2A. No PLLVR (that is GW1NSR-only).

set HERE [file dirname [info script]]
set ROOT [file normalize [file join $HERE ../..]]
set GOWIN [file join $ROOT gowin]

set_device -name GW2A-18C GW2A-LV18PG256C8/I7

add_file -type verilog [file join $GOWIN src CPUMinimalWrapper.v]
add_file -type verilog [file join $ROOT generated InstrRom.v]
add_file -type verilog [file join $ROOT generated HwMul.v]
add_file -type verilog [file join $HERE blink3_top.v]
add_file -type verilog [file join $GOWIN ip gowin_sp.v]
add_file -type cst     [file join $HERE primer20k.cst]
add_file -type sdc     [file join $HERE primer20k.sdc]

set_option -top_module blink3_top
set_option -verilog_std sysv2017
if {[info exists ::env(GOWIN_OUT_NAME)] && $::env(GOWIN_OUT_NAME) ne ""} {
  set_option -output_base_name $::env(GOWIN_OUT_NAME)
} else {
  set_option -output_base_name blink3
}
set_option -synthesis_tool gowinsynthesis
set_option -place_option 2
# C13 is DONE, A13 is READY. Leave MSPI/JTAG dedicated so SRAM load works.
set_option -use_done_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 0
set_option -use_jtag_as_gpio 0

run all
