// CPUSimTop plus the SPI disk model. The model is clocked by the bridge
// clock. The CPU and its shifter run at half that rate, inside CPUSimTop.
module disk_boot_top (
  input  wire clock,
  input  wire reset,
  output wire led,
  output wire halted,
  output wire [31:0] pc,
  output wire [39:0] mask,
  output wire [31:0] r5,
  output wire [31:0] r9,
  output wire mem_write,
  output wire [31:0] mem_addr,
  output wire screen_we,
  output wire [31:0] bmp_data,
  output wire [12:0] bmp_word,
  output wire status_we,
  output wire [8:0] status_word,
  output wire armed,
  // Active-low, like S1. Held high unless the bench is pausing.
  input  wire btn_n
);
  wire cs_n;
  wire sclk;
  wire mosi;
  wire miso;
  wire cpu_clk;
  wire pressed;

  CPUSimTop cpu (
    .clock(clock),
    .reset(reset),
    .io_led(led),
    .io_halted(halted),
    .io_pc(pc),
    .io_mask(mask),
    .io_r5(r5),
    .io_r9(r9),
    .io_spiCsN(cs_n),
    .io_spiClk(sclk),
    .io_spiMosi(mosi),
    .io_spiMiso(miso),
    .io_memWrite(mem_write),
    .io_memAddr(mem_addr),
    .io_screenWe(screen_we),
    .io_bmpData(bmp_data),
    .io_bmpWord(bmp_word),
    .io_statusWe(status_we),
    .io_statusWord(status_word),
    .io_diskValid(1'b0),
    .io_diskWord(32'd0),
    .io_diskTake(),
    .io_cpuClk(cpu_clk),
    .io_armed(armed),
    .io_btnPressed(pressed)
  );

  // The NOR image has no disk on this UART. The bench drives the button.
  button_gate #(.CLKS_PER_BIT(117)) u_gate (
    .clk(cpu_clk),
    .resetn(~reset),
    .btn_n(btn_n),
    .uart_rx(1'b1),
    .pressed(pressed)
  );

  spi_disk_model flash (
    .clk(clock),
    .cs_n(cs_n),
    .sclk(sclk),
    .mosi(mosi),
    .miso(miso)
  );
endmodule
