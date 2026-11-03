# Primer 20K Dock blinky. Device: GW2A-LV18PG256C8/I7 (GW2A-18C).
# Invoked from tools/gowin_build_primer20k.sh. Do not run with
# QT_QPA_PLATFORM=offscreen (gw_sh crashes). SRAM-loadable .fs only.

set HERE [file dirname [info script]]

set_device -name GW2A-18C GW2A-LV18PG256C8/I7

# tools/gowin_build_primer20k.sh writes led_build.v with `define COUNT_VALUE.
add_file -type verilog [file join $HERE led_build.v]
add_file -type cst     [file join $HERE primer20k.cst]
add_file -type sdc     [file join $HERE primer20k.sdc]

set_option -top_module led
set_option -verilog_std sysv2017
set_option -synthesis_tool gowinsynthesis
set_option -place_option 2
set_option -output_base_name primer20k_blink

# C13 is DONE, A13 is READY. Leave MSPI/JTAG dedicated so SRAM load works.
set_option -use_done_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 0
set_option -use_jtag_as_gpio 0

run all
