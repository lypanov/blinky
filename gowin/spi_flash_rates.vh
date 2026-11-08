// Published blink half-periods for the Nano 4K SPI-flash pathfinder.
// The PLLVR bypass clock is 27 MHz. A 50% blink at f Hz uses
// HALF = 27_000_000 / (2 * f) cycles.
//
//   A  1.5 Hz  JEDEC ID 85 60 16 (Puya P25Q32, 32 Mbit)
//   B  2.5 Hz  last-sector erase, page program, read-back match
//   C  4.0 Hz  fresh SRAM load reads the same page and build
//
// BUILD_YES is the byte written into the page. BUILD_NO is the
// negative reader: same rate C, and the LED must stay dark.
// The only flash address these images touch is the first page of
// the last 4 KB sector.

`define SPI_RATE_A_HALF 9000000
`define SPI_RATE_B_HALF 5400000
`define SPI_RATE_C_HALF 3375000
`define SPI_BUILD_YES 8'h7B
`define SPI_BUILD_NO 8'h7C
`define SPI_PAGE_ADDR 24'h3FF000
