// Published constants for the Nano 4K flash-disk reader.
// The PLLVR bypass clock is 27 MHz. A 50% blink at 2.0 Hz uses
// HALF = 27_000_000 / (2 * 2) = 6_750_000 cycles.
//
// The reader is SRAM-loaded. It only issues 03h reads at DISK_BASE.
// BUILD is the build number in the disk header. BUILD_NEG is the
// negative reader: same rate, and the LED must stay dark.
// tools/build_disk_image.py must keep these numbers.

`ifndef DISK_RATES
`define DISK_RATES

`define DISK_MAGIC       32'h314B5344
`define DISK_VERSION     32'h00000001
`define DISK_BUILD       32'h000000D1
`define DISK_BUILD_NEG   32'h000000D2
`define DISK_BASE        24'h200000
`define DISK_BLINK_HALF  6750000
`define DISK_HEADER_BYTES 20

`endif
