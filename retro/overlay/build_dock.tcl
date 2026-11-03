# NESTang v0.4 for Tang Primer 20K Dock. SRAM-loadable .fs only.
# Run from retro/nestang after applying nestang_dock.cst.patch:
#   QT_QPA_PLATFORM=xcb gw_sh ../overlay/build_dock.tcl

set_device -name GW2A-18C GW2A-LV18PG256C8/I7

add_file -type verilog src/MicroCode.v
add_file -type verilog src/apu.v
add_file -type verilog src/compat.v
add_file -type verilog src/config.sv
add_file -type verilog src/cpu.v
add_file -type verilog src/ddr3_controller.v
add_file -type verilog src/ddr3_tester.v
add_file -type verilog src/dsp.v
add_file -type verilog src/game_loader.v
add_file -type verilog src/gowin_clkdiv/gowin_clkdiv.v
add_file -type verilog src/gowin_rpll_hdmi/gowin_rpll.v
add_file -type verilog src/gowin_rpll_nes/gowin_rpll.v
add_file -type verilog src/hdmi2/audio_clock_regeneration_packet.sv
add_file -type verilog src/hdmi2/audio_info_frame.sv
add_file -type verilog src/hdmi2/audio_sample_packet.sv
add_file -type verilog src/hdmi2/auxiliary_video_information_info_frame.sv
add_file -type verilog src/hdmi2/hdmi.sv
add_file -type verilog src/hdmi2/packet_assembler.sv
add_file -type verilog src/hdmi2/packet_picker.sv
add_file -type verilog src/hdmi2/serializer.sv
add_file -type verilog src/hdmi2/source_product_description_info_frame.sv
add_file -type verilog src/hdmi2/tmds_channel.sv
add_file -type verilog src/hw_sound.v
add_file -type verilog src/hw_uart.v
add_file -type verilog src/memory_controller.v
add_file -type verilog src/mmu.v
add_file -type verilog src/nes.v
add_file -type verilog src/nes2hdmi.sv
add_file -type verilog src/nes_tang20k.v
add_file -type verilog src/ppu.v
add_file -type verilog src/sdram.v
add_file -type verilog src/uart_tx_V2.v
add_file -type cst src/nestang_dock.cst
add_file -type sdc src/nestang.sdc

set_option -top_module NES_Tang20k
set_option -verilog_std sysv2017
set_option -synthesis_tool gowinsynthesis
set_option -place_option 2
set_option -output_base_name nestang_dock
set_option -include_path src

# Dual-purpose pins used by Dock HDMI/DDR/LEDs. Never steal JTAG.
set_option -use_sspi_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
set_option -use_i2c_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_jtag_as_gpio 0

run all
