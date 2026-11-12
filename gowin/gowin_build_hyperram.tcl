# Tang Nano 4K, HyperRAM data port. Device GW1NSR-LV4CQN48PC6/I5.
# Invoked from tools/gowin_build.sh with FPGA_IMAGE=hyperram.
# Do not run with QT_QPA_PLATFORM=offscreen.

set ROOT [file normalize [file join [file dirname [info script]] ..]]
set OUT  [file join $ROOT gowin]
set IP   [file join $OUT ip hpram]
set DATA /opt/gowin-eda-ide/ipcore/HYPERRAM/data

# Gowin accepts one include directory. Link the encrypted IP next to
# our hpram_define.v and hpram_param.v so both are found. The links are
# gitignored; they point at this machine's Gowin install.
foreach f {hpram_local_define.v hpram_local_param.v hpram_code_1N2A.v HPRAM_TOP.v} {
  set dest [file join $IP $f]
  if {![file exists $dest]} {
    file link -symbolic $dest [file join $DATA $f]
  }
}

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5

# off, flash, or square. Text is a later step.
set vmode "off"
if {[info exists ::env(VIDEO_MODE)] && $::env(VIDEO_MODE) ne ""} {
  set vmode $::env(VIDEO_MODE)
}
if {$vmode ne "off" && $vmode ne "flash" && $vmode ne "square"} {
  puts stderr "error: VIDEO_MODE=$vmode is not this step"
  exit 1
}
set vh [open [file join $IP video_mode.vh] w]
puts $vh "`ifndef VIDEO_MODE_INCLUDED"
puts $vh "`define VIDEO_MODE_INCLUDED"
if {$vmode eq "flash"} {
  puts $vh "`define VIDEO_ON"
} elseif {$vmode eq "square"} {
  puts $vh "`define VIDEO_ON"
  puts $vh "`define VIDEO_SQUARE"
} else {
  puts $vh "// VIDEO_MODE=off"
}
puts $vh "`endif"
close $vh

set_option -include_path $IP

add_file -type verilog [file join $OUT src CPUMinimalWrapper.v]
add_file -type verilog [file join $OUT KeepBit.v]
add_file -type verilog [file join $ROOT generated InstrRom.v]
add_file -type verilog [file join $ROOT generated HwMul.v]
add_file -type verilog [file join $OUT FpSnap.v]
if {[info exists ::env(SECTOR_ROM)] && $::env(SECTOR_ROM) ne ""} {
  add_file -type verilog $::env(SECTOR_ROM)
}
add_file -type verilog [file join $OUT blinky_top_hyperram.v]
add_file -type verilog [file join $OUT button_gate.v]
add_file -type verilog [file join $OUT ip gowin_sp.v]
add_file -type verilog [file join $OUT ip hpram_pllvr.v]
add_file -type verilog [file join $OUT ip gowin_clkdiv2.v]
add_file -type verilog [file join $IP HPRAM_TOP.v]
add_file -type verilog [file join $IP hpram_code_1N2A.v]
if {$vmode eq "flash" || $vmode eq "square"} {
  add_file -type verilog [file join $OUT video.v]
  add_file -type cst     [file join $ROOT tang-nano-4k-hdmi.cst]
} else {
  add_file -type cst     [file join $ROOT tang-nano-4k.cst]
}
add_file -type sdc     [file join $OUT blinky.sdc]

set_option -top_module blinky_top
set_option -verilog_std sysv2017
if {[info exists ::env(GOWIN_OUT_NAME)] && $::env(GOWIN_OUT_NAME) ne ""} {
  set_option -output_base_name $::env(GOWIN_OUT_NAME)
} else {
  set_option -output_base_name hyperram_n262144
}
set_option -synthesis_tool gowinsynthesis
# place_option 2 met timing and left the LED dark for the arm
# constant of this disk. place_option 0 arms that same constant.
set_option -place_option 0
set_option -use_mspi_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
set_option -use_jtag_as_gpio 0
# Post-place file names the MULT36X36 site. Placement is unchanged.
set_option -gen_posp 1

run all
