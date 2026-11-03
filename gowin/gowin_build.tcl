# Recreate the Tang Nano 4K Gowin project and run syn+PNR.
# Device: GW1NSR-LV4CQN48PC6/I5 (GW1NSR-4C, QN48P). Top: CPUMinimalWrapper.
# Invoked from tools/gowin_build.sh; do not run with QT_QPA_PLATFORM=offscreen.

set ROOT [file normalize [file join [file dirname [info script]] ..]]
set OUT  [file join $ROOT gowin]

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5

add_file -type verilog [file join $OUT src CPUMinimalWrapper.v]
add_file -type verilog [file join $OUT blinky_top.v]
add_file -type verilog [file join $OUT ip gowin_sp.v]
add_file -type verilog [file join $OUT ip gowin_pllvr.v]
# gowin/ip/*.ipc are IP-generator configs. Do not add them here: syn uses Verilog.
add_file -type cst     [file join $ROOT tang-nano-4k.cst]
add_file -type sdc     [file join $OUT blinky.sdc]

set_option -top_module blinky_top
set_option -verilog_std sysv2017
set_option -output_base_name blink2hw_4x
set_option -synthesis_tool gowinsynthesis
set_option -place_option 2
# blinky_top only brings out clock/reset/led/uart — keep MSPI/JTAG as dedicated.
set_option -use_mspi_as_gpio 0
set_option -use_sspi_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
# Never steal the JTAG pins — we SRAM-load through them.
set_option -use_jtag_as_gpio 0

run all
