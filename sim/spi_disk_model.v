// Small SPI NOR model for the disk reader.
// Mode 0, MSB first. Implements 03h from BASE. The array is loaded from
// a file (the disk image) or left blank. Any other command is counted
// and ignored. Addresses outside the loaded image return FF.

module spi_disk_model #(
  parameter [23:0] BASE = 24'h200000,
  // PAGE_LIMIT is 80 sectors plus the 20-byte header, 81940 bytes.
  // Texts.rsc took the image past 64KB.
  parameter integer MAXB = 131072,
  parameter integer LOAD = 1,
  parameter FILE = "sim/out/disk.bin"
) (
  input wire clk,
  input wire cs_n,
  input wire sclk,
  input wire mosi,
  output reg miso
);
  reg [7:0] mem [0:MAXB-1];
  integer nbytes;
  integer read_cmds;
  integer other_cmds;
  integer bad_addr;
  integer bytes_out;
  reg [23:0] first_addr;
  reg have_addr;

  reg cs_q;
  reg sclk_q;
  reg [2:0] bitn;
  reg [7:0] shin;
  reg [7:0] shout;
  reg [7:0] cmd;
  reg [23:0] addr;
  reg [1:0] addr_n;
  reg [1:0] phase;
  reg [2:0] read_bit;
  reg reading;
  integer ki;

  initial begin
    miso = 1'b1;
    cs_q = 1'b1;
    sclk_q = 1'b0;
    bitn = 3'd0;
    shin = 8'd0;
    shout = 8'd0;
    cmd = 8'd0;
    addr = 24'd0;
    addr_n = 2'd0;
    phase = 2'd0;
    read_bit = 3'd0;
    reading = 1'b0;
    nbytes = 0;
    read_cmds = 0;
    other_cmds = 0;
    bad_addr = 0;
    bytes_out = 0;
    first_addr = 24'd0;
    have_addr = 1'b0;
    for (ki = 0; ki < MAXB; ki = ki + 1)
      mem[ki] = 8'hFF;
    if (LOAD != 0) begin
      ki = $fopen(FILE, "rb");
      if (ki == 0) begin
        $display("SPI_DISK model cannot open %0s", FILE);
        $fatal(1);
      end
      nbytes = $fread(mem, ki);
      if ($fgetc(ki) >= 0) begin
        $display("SPI_DISK file is larger than %0d bytes", MAXB);
        $fatal(1);
      end
      $fclose(ki);
      if (nbytes <= 0 || nbytes > MAXB) begin
        $display("SPI_DISK model read %0d bytes from %0s", nbytes, FILE);
        $fatal(1);
      end
    end else begin
      nbytes = 256;
    end
  end

  function [7:0] at;
    input [23:0] a;
    integer off;
    begin
      if (a < BASE) begin
        at = 8'hFF;
      end else begin
        off = a - BASE;
        if (off < nbytes)
          at = mem[off];
        else
          at = 8'hFF;
      end
    end
  endfunction

  task note_addr;
    input [23:0] a;
    begin
      if (!have_addr) begin
        first_addr = a;
        have_addr = 1'b1;
      end
      bytes_out = bytes_out + 1;
      if (a < BASE || a - BASE >= nbytes)
        bad_addr = bad_addr + 1;
    end
  endtask

  task start_read;
    input [7:0] data;
    begin
      reading = 1'b1;
      read_bit = 3'd0;
      miso = data[7];
      shout = {data[6:0], 1'b0};
    end
  endtask

  task advance_read;
    input [7:0] next_byte;
    begin
      if (read_bit == 3'd7) begin
        read_bit = 3'd0;
        miso = next_byte[7];
        shout = {next_byte[6:0], 1'b0};
      end else begin
        // The first sample of a byte is the one the master took. Count
        // that byte, not the lookahead the next rising edge may never clock.
        if (read_bit == 3'd0)
          note_addr(addr);
        read_bit = read_bit + 3'd1;
        miso = shout[7];
        shout = {shout[6:0], 1'b0};
      end
    end
  endtask

  reg [7:0] just;
  reg [23:0] full;
  reg [7:0] rd;

  always @(posedge clk) begin
    cs_q <= cs_n;
    sclk_q <= sclk;

    if ((cs_q == 1'b1) && (cs_n == 1'b0)) begin
      bitn <= 3'd0;
      phase <= 2'd0;
      reading <= 1'b0;
      addr_n <= 2'd0;
      cmd <= 8'd0;
      shin <= 8'd0;
    end else if ((cs_n == 1'b0) && (sclk_q == 1'b0) && (sclk == 1'b1)) begin
      just = {shin[6:0], mosi};
      shin <= {shin[6:0], mosi};
      if (reading) begin
        if (read_bit == 3'd7) begin
          addr <= addr + 24'd1;
          rd = at(addr + 24'd1);
        end
        advance_read(rd);
      end else if (bitn == 3'd7) begin
        bitn <= 3'd0;
        if (phase == 2'd0) begin
          cmd <= just;
          if (just == 8'h03) begin
            phase <= 2'd1;
            addr_n <= 2'd0;
            read_cmds <= read_cmds + 1;
          end else begin
            other_cmds <= other_cmds + 1;
            phase <= 2'd3;
          end
        end else if (phase == 2'd1) begin
          if (addr_n == 2'd0) begin
            addr[23:16] <= just;
            addr_n <= 2'd1;
          end else if (addr_n == 2'd1) begin
            addr[15:8] <= just;
            addr_n <= 2'd2;
          end else begin
            full = {addr[23:8], just};
            addr <= full;
            rd = at(full);
            phase <= 2'd2;
            start_read(rd);
          end
        end
      end else begin
        bitn <= bitn + 3'd1;
      end
    end

    if ((cs_q == 1'b0) && (cs_n == 1'b1)) begin
      reading <= 1'b0;
      miso <= 1'b1;
      cmd <= 8'd0;
    end
  end
endmodule
