// HyperRAM stand-in for the Dock UART disk boot.
// The word assembler is the FPGA module, clocked by the CPU clock.
// The sender waits until the CPU is out of reset, then shifts disk.bin
// at 16 CPU clocks a bit. The FPGA uses 210; the ratio is the proof.
module uart_disk_top (
  input  wire clock,
  input  wire reset,
  output wire led,
  output wire halted,
  output wire [31:0] pc,
  output wire [39:0] mask,
  output wire [31:0] r2,
  output wire [31:0] r5,
  output wire [31:0] r9,
  output wire mem_write,
  output wire [31:0] mem_addr,
  output wire screen_we
);
  wire cpu_clk;
  wire disk_valid;
  wire disk_take;
  wire [31:0] disk_word;
  wire tx;

  CPUSimTop cpu (
    .clock(clock),
    .reset(reset),
    .io_led(led),
    .io_halted(halted),
    .io_pc(pc),
    .io_mask(mask),
    .io_r2(r2),
    .io_r5(r5),
    .io_r9(r9),
    .io_spiCsN(),
    .io_spiClk(),
    .io_spiMosi(),
    .io_spiMiso(1'b0),
    .io_memWrite(mem_write),
    .io_memAddr(mem_addr),
    .io_screenWe(screen_we),
    .io_diskValid(disk_valid),
    .io_diskWord(disk_word),
    .io_diskTake(disk_take),
    .io_cpuClk(cpu_clk)
  );

  uart_word_rx #(.CLKS_PER_BIT(16)) u_disk_rx (
    .clk(cpu_clk),
    .resetn(~reset),
    .rx(tx),
    .valid(disk_valid),
    .word(disk_word),
    .take(disk_take)
  );

  uart_disk_send #(.CLKS_PER_BIT(16)) u_send (
    .clk(cpu_clk),
    .resetn(~reset),
    .tx(tx)
  );
endmodule

// 8N1, LSB first. One stop bit, then the next start bit.
module uart_disk_send #(
  parameter integer CLKS_PER_BIT = 16
) (
  input  wire clk,
  input  wire resetn,
  output reg  tx
);
  reg [7:0] mem [0:32767];
  integer nbytes;
  integer idx;
  integer wait_n;
  integer bidx;
  integer timer;
  reg [7:0] cur;

  initial begin : load
    reg [8*512-1:0] path;
    integer fd;
    integer n;
    if (!$value$plusargs("disk=%s", path))
      path = "sim/out/disk.bin";
    fd = $fopen(path, "rb");
    if (fd == 0) begin
      $display("FAIL cannot open disk");
      $finish;
    end
    n = $fread(mem, fd);
    $fclose(fd);
    if (n <= 0 || n > 32768) begin
      $display("FAIL disk length %0d", n);
      $finish;
    end
    nbytes = n;
  end

  initial begin
    tx = 1'b1;
    idx = 0;
    wait_n = 0;
    bidx = 0;
    timer = 0;
    cur = 8'd0;
  end

  always @(posedge clk) begin
    if (!resetn) begin
      tx <= 1'b1;
      idx <= 0;
      wait_n <= 0;
      bidx <= 0;
      timer <= 0;
    end else if (wait_n < 64) begin
      tx <= 1'b1;
      wait_n <= wait_n + 1;
    end else if (idx >= nbytes) begin
      tx <= 1'b1;
    end else begin
      if (bidx == 0 && timer == 0)
        cur <= mem[idx];
      if (bidx == 0)
        tx <= 1'b0;
      else if (bidx <= 8)
        tx <= cur[bidx - 1];
      else
        tx <= 1'b1;
      if (timer == CLKS_PER_BIT - 1) begin
        timer <= 0;
        if (bidx == 9) begin
          bidx <= 0;
          idx <= idx + 1;
        end else
          bidx <= bidx + 1;
      end else
        timer <= timer + 1;
    end
  end
endmodule
