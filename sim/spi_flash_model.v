// Small SPI NOR model for the Nano 4K pathfinder.
// Mode 0, MSB first. Implements 9Fh, 05h, 06h, 20h, 02h, and 03h.
// The array is the last 4 KB sector only. Any other address is refused
// and counted in bad_addr. Erase and page program set WIP for WIP_CYCLES
// system clocks, then clear it and WEL.

module spi_flash_model #(
  parameter [7:0] ID0 = 8'h85,
  parameter [7:0] ID1 = 8'h60,
  parameter [7:0] ID2 = 8'h16,
  parameter integer WIP_CYCLES = 200
) (
  input wire clk,
  input wire cs_n,
  input wire sclk,
  input wire mosi,
  output reg miso
);
  localparam [23:0] PAGE = 24'h3FF000;

  reg [7:0] mem [0:4095];
  reg cs_q;
  reg sclk_q;
  reg [2:0] bitn;
  reg [7:0] shin;
  reg [7:0] shout;
  reg [7:0] cmd;
  reg [23:0] addr;
  reg [1:0] addr_n;
  reg [2:0] phase;
  reg [2:0] read_bit;
  reg reading;
  reg [1:0] idn;
  reg wel;
  reg [15:0] wip_left;
  reg addr_ok;
  reg prog_ok;
  reg [23:0] pend_addr;
  integer erase_count;
  integer prog_count;
  integer prog_bytes;
  integer prog_len;
  integer bad_addr;
  integer bad_cmd;
  integer status_reads;
  integer wip_seen;
  reg [23:0] erase_addr;
  reg [23:0] prog_addr;
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
    phase = 3'd0;
    read_bit = 3'd0;
    reading = 1'b0;
    idn = 2'd0;
    wel = 1'b0;
    wip_left = 16'd0;
    addr_ok = 1'b0;
    prog_ok = 1'b0;
    pend_addr = 24'd0;
    erase_count = 0;
    prog_count = 0;
    prog_bytes = 0;
    prog_len = 0;
    bad_addr = 0;
    bad_cmd = 0;
    status_reads = 0;
    wip_seen = 0;
    erase_addr = 24'd0;
    prog_addr = 24'd0;
    for (ki = 0; ki < 4096; ki = ki + 1)
      mem[ki] = 8'hFF;
  end

  function [7:0] status_byte;
    input wel_i;
    input wip_i;
    begin
      status_byte = {6'b000000, wel_i, wip_i};
    end
  endfunction

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
    input more;
    begin
      if (read_bit == 3'd7) begin
        read_bit = 3'd0;
        if (more) begin
          miso = next_byte[7];
          shout = {next_byte[6:0], 1'b0};
        end else begin
          reading = 1'b0;
          miso = 1'b1;
        end
      end else begin
        read_bit = read_bit + 3'd1;
        miso = shout[7];
        shout = {shout[6:0], 1'b0};
      end
    end
  endtask

  reg [7:0] just;
  reg [7:0] st;
  reg [23:0] full;
  reg [7:0] rd;

  always @(posedge clk) begin
    cs_q <= cs_n;
    sclk_q <= sclk;

    if ((cs_q == 1'b1) && (cs_n == 1'b0)) begin
      bitn <= 3'd0;
      phase <= 3'd0;
      reading <= 1'b0;
      addr_n <= 2'd0;
      addr_ok <= 1'b0;
      prog_ok <= 1'b0;
      cmd <= 8'd0;
      prog_bytes <= 0;
      shin <= 8'd0;
    end else if ((cs_n == 1'b0) && (sclk_q == 1'b0) && (sclk == 1'b1)) begin
      just = {shin[6:0], mosi};
      shin <= {shin[6:0], mosi};
      if (reading) begin
        if (cmd == 8'h9F) begin
          if (idn == 2'd0)
            advance_read(ID1, 1'b1);
          else if (idn == 2'd1)
            advance_read(ID2, 1'b1);
          else
            advance_read(8'hFF, 1'b0);
          if (read_bit == 3'd0 && idn != 2'd2)
            idn <= idn + 2'd1;
          else if (read_bit == 3'd0 && idn == 2'd2)
            idn <= 2'd3;
        end else if (cmd == 8'h05) begin
          advance_read(8'hFF, 1'b0);
        end else if (cmd == 8'h03) begin
          if (read_bit == 3'd7) begin
            if (addr[23:12] == 12'h3FF && addr != 24'h3FFFFF)
              rd = mem[addr[11:0] + 12'd1];
            else
              rd = 8'hFF;
            if (addr[23:12] != 12'h3FF)
              bad_addr <= bad_addr + 1;
            addr <= addr + 24'd1;
          end
          advance_read(rd, 1'b1);
        end
      end else if (bitn == 3'd7) begin
        bitn <= 3'd0;
        if (phase == 3'd0) begin
          cmd <= just;
          case (just)
            8'h9F: begin
              idn <= 2'd0;
              phase <= 3'd3;
              start_read(ID0);
              reading <= 1'b1;
            end
            8'h05: begin
              st = status_byte(wel, wip_left != 16'd0);
              phase <= 3'd3;
              start_read(st);
              reading <= 1'b1;
              status_reads <= status_reads + 1;
              if (wip_left != 16'd0)
                wip_seen <= wip_seen + 1;
            end
            8'h06: phase <= 3'd4;
            8'h20, 8'h02, 8'h03: begin
              phase <= 3'd1;
              addr_n <= 2'd0;
            end
            default: bad_cmd <= bad_cmd + 1;
          endcase
        end else if (phase == 3'd1) begin
          if (addr_n == 2'd0) begin
            addr[23:16] <= just;
            addr_n <= 2'd1;
          end else if (addr_n == 2'd1) begin
            addr[15:8] <= just;
            addr_n <= 2'd2;
          end else begin
            full = {addr[23:8], just};
            addr <= full;
            pend_addr <= full;
            addr_ok <= 1'b1;
            if (full != PAGE)
              bad_addr <= bad_addr + 1;
            if (cmd == 8'h03) begin
              phase <= 3'd3;
              if (full == PAGE)
                rd = mem[full[11:0]];
              else
                rd = 8'hFF;
              start_read(rd);
              reading <= 1'b1;
            end else if (cmd == 8'h02) begin
              phase <= 3'd2;
              prog_ok <= (full == PAGE);
              if (full == PAGE)
                prog_addr <= full;
            end else begin
              phase <= 3'd4;
            end
          end
        end else if (phase == 3'd2) begin
          if (prog_ok) begin
            mem[pend_addr[11:0]] <= mem[pend_addr[11:0]] & just;
            pend_addr <= {pend_addr[23:8], pend_addr[7:0] + 8'd1};
          end
          prog_bytes <= prog_bytes + 1;
        end
      end else begin
        bitn <= bitn + 3'd1;
      end
    end

    if ((cs_q == 1'b0) && (cs_n == 1'b1)) begin
      reading <= 1'b0;
      miso <= 1'b1;
      if (cmd == 8'h06 && wip_left == 16'd0)
        wel <= 1'b1;
      else if (cmd == 8'h20 && wel && wip_left == 16'd0 && addr_ok) begin
        wel <= 1'b0;
        wip_left <= WIP_CYCLES[15:0];
        if (pend_addr == PAGE) begin
          erase_count <= erase_count + 1;
          erase_addr <= pend_addr;
          for (ki = 0; ki < 4096; ki = ki + 1)
            mem[ki] <= 8'hFF;
        end
      end       else if (cmd == 8'h02 && wel && wip_left == 16'd0 && addr_ok && prog_bytes != 0) begin
        wel <= 1'b0;
        wip_left <= WIP_CYCLES[15:0];
        prog_len <= prog_bytes;
        if (prog_addr == PAGE)
          prog_count <= prog_count + 1;
      end
      cmd <= 8'd0;
    end else if (wip_left != 16'd0) begin
      wip_left <= wip_left - 16'd1;
    end
  end
endmodule
