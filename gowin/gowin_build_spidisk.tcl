# Tang Nano 4K flash-disk reader. SRAM bitstream only.
# Device: GW1NSR-LV4CQN48PC6/I5 (GW1NSR-4C, QN48P). Top: spi_disk_top.
# The NOR pins are the pathfinder's pins. Invoked from tools/gowin_build_spidisk.sh.

set ROOT [file normalize [file join [file dirname [info script]] ..]]
set OUT  [file join $ROOT gowin]

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5

add_file -type verilog [file join $OUT spi_flash_pathfinder.v]
add_file -type verilog [file join $OUT spi_disk_reader.v]
add_file -type verilog [file join $OUT spi_disk_top.v]
add_file -type verilog [file join $OUT ip gowin_pllvr.v]
add_file -type cst     [file join $OUT spi_flash.cst]
add_file -type sdc     [file join $OUT spi_flash.sdc]

set_option -top_module spi_disk_top
set_option -verilog_std sysv2017
if {[info exists ::env(GOWIN_OUT_NAME)] && $::env(GOWIN_OUT_NAME) ne ""} {
  set_option -output_base_name $::env(GOWIN_OUT_NAME)
} else {
  set_option -output_base_name spi_disk_read
}
set_option -synthesis_tool gowinsynthesis
set_option -place_option 0
# MSPI pins are the external NOR. After SRAM configuration they are
# ordinary I/O. This is the IDE option "Use MSPI as Regular IO".
set_option -use_mspi_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_ready_as_gpio 1
# Pin 9 is DONE and the flash HOLD# pin.
set_option -use_done_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
# JTAG stays the SRAM-load port.
set_option -use_jtag_as_gpio 0

run all
