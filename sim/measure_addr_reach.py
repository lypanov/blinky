#!/usr/bin/env python3
"""Drive the elaborated memory bridges and print the address each keeps.

The HyperRAM bridge is the module in the NOR-disk elaboration. The DDR3
bridge is the module in the Dock elaboration. Neither file is edited.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Byte address, expected controller address.
# HyperRAM: lineAddr = {cpu[22:4], 3'b000}. Bits above 22 alias.
HYPER = [
    (0x00000000, 0x000000),
    (0x00000010, 0x000008),
    (0x007FFFF0, 0x3FFFF8),
    (0x00800000, 0x000000),
    (0x00800010, 0x000008),
    (0x00FFFFF0, 0x3FFFF8),
]
# DDR3, word store, first beat: addr = cpu[26:1]. Bits above 26 alias.
DDR = [
    (0x00000000, 0x0000000),
    (0x00000010, 0x0000008),
    (0x04000000, 0x2000000),
    (0x07FFFFF0, 0x3FFFFF8),
    (0x08000000, 0x0000000),
    (0x08000010, 0x0000008),
]


def _extract(path: str, module: str, dest: str) -> None:
    text = open(path, "r", encoding="ascii", errors="replace").read().splitlines(True)
    start = next(i for i, line in enumerate(text) if line.startswith(f"module {module}("))
    end = next(i for i in range(start, len(text)) if text[i].startswith("endmodule"))
    open(dest, "w", encoding="ascii").write("".join(text[start : end + 1]))


def _run(work: str, sources: list[str], top: str) -> str:
    sim = os.path.join(work, top)
    cmd = ["iverilog", "-g2012", "-o", sim, "-s", top, *sources]
    subprocess.run(cmd, check=True)
    out = subprocess.run(["vvp", sim], check=True, capture_output=True, text=True)
    if out.stderr.strip():
        sys.stderr.write(out.stderr)
    return out.stdout


def _hyper_tb() -> str:
    rows = "\n".join(
        f"    poke(32'h{addr:08X}, 22'h{want:06X});" for addr, want in HYPER
    )
    return textwrap.dedent(
        f"""
        `timescale 1ns/1ps
        module tb_hyper;
          reg clock, reset, write, read, is_byte, calib, valid;
          reg [31:0] addr, wdata, rd_data;
          wire [31:0] rdata, hr_data;
          wire stall, cmd, cmd_en;
          wire [21:0] hr_addr;
          wire [3:0] mask;
          HyperRamBridge dut(
            .clock(clock), .reset(reset),
            .io_cpuAddr(addr), .io_cpuWriteData(wdata),
            .io_cpuWrite(write), .io_cpuRead(read), .io_cpuByte(is_byte),
            .io_cpuReadData(rdata), .io_memStall(stall),
            .io_hr_cmd(cmd), .io_hr_cmd_en(cmd_en), .io_hr_addr(hr_addr),
            .io_hr_wr_data(hr_data), .io_hr_data_mask(mask),
            .io_hr_rd_data(rd_data), .io_hr_rd_data_valid(valid),
            .io_hr_init_calib(calib)
          );
          initial clock = 0;
          always #5 clock = ~clock;
          task poke(input [31:0] a, input [21:0] want);
            integer i;
            reg seen;
            begin
              reset = 1; write = 0; read = 0; is_byte = 0;
              addr = 0; wdata = 32'h1; valid = 0; rd_data = 0; calib = 1;
              repeat (4) @(posedge clock);
              reset = 0;
              @(posedge clock);
              addr = a; write = 1;
              @(posedge clock);
              write = 0;
              seen = 0;
              for (i = 0; i < 40; i = i + 1) begin
                #1;
                if (cmd_en && !seen) begin
                  $display("HYPER byte %08x line %06x", a, hr_addr);
                  if (hr_addr !== want) begin
                    $display("FAIL hyper %08x got %06x want %06x", a, hr_addr, want);
                    $finish(1);
                  end
                  seen = 1;
                end
                @(posedge clock);
              end
              if (!seen) begin
                $display("FAIL hyper %08x never issued", a);
                $finish(1);
              end
            end
          endtask
          initial begin
        {rows}
            $display("HYPER ok");
            $finish;
          end
        endmodule
        """
    )


def _ddr_tb() -> str:
    rows = "\n".join(
        f"    poke(32'h{addr:08X}, 26'h{want:07X});" for addr, want in DDR
    )
    return textwrap.dedent(
        f"""
        `timescale 1ns/1ps
        module tb_ddr;
          reg clock, reset, write, read, is_byte, calib, busy, ready;
          reg [31:0] addr, wdata;
          reg [15:0] dout;
          wire [31:0] rdata;
          wire stall, rd, wr, refresh;
          wire [25:0] ddr_addr;
          wire [15:0] din;
          Ddr3Bridge dut(
            .clock(clock), .reset(reset),
            .io_cpuAddr(addr), .io_cpuWriteData(wdata),
            .io_cpuWrite(write), .io_cpuRead(read), .io_cpuByte(is_byte),
            .io_cpuReadData(rdata), .io_memStall(stall),
            .io_ddr_rd(rd), .io_ddr_wr(wr), .io_ddr_refresh(refresh),
            .io_ddr_addr(ddr_addr), .io_ddr_din(din),
            .io_ddr_dout(dout), .io_ddr_data_ready(ready),
            .io_ddr_busy(busy), .io_ddr_calib(calib)
          );
          initial clock = 0;
          always #5 clock = ~clock;
          task poke(input [31:0] a, input [25:0] want);
            integer i;
            reg seen;
            begin
              reset = 1; write = 0; read = 0; is_byte = 0;
              addr = 0; wdata = 32'hA5A5_5A5A; dout = 0; ready = 0;
              busy = 0; calib = 1;
              repeat (4) @(posedge clock);
              reset = 0;
              @(posedge clock);
              addr = a; write = 1;
              @(posedge clock);
              write = 0;
              seen = 0;
              for (i = 0; i < 80; i = i + 1) begin
                #1;
                if (wr && !seen) begin
                  $display("DDR byte %08x half %07x bank %0d row %04x col %03x",
                    a, ddr_addr, ddr_addr[25:23], ddr_addr[22:10], ddr_addr[9:0]);
                  if (ddr_addr !== want) begin
                    $display("FAIL ddr %08x got %07x want %07x", a, ddr_addr, want);
                    $finish(1);
                  end
                  seen = 1;
                end
                @(posedge clock);
              end
              if (!seen) begin
                $display("FAIL ddr %08x never wrote", a);
                $finish(1);
              end
            end
          endtask
          initial begin
        {rows}
            $display("DDR ok");
            $finish;
          end
        endmodule
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hyper", required=True)
    parser.add_argument("--ddr", required=True)
    parser.add_argument("--work", default="/tmp/addr-reach")
    args = parser.parse_args()
    os.makedirs(args.work, exist_ok=True)
    hyper_v = os.path.join(args.work, "HyperRamBridge.v")
    ddr_v = os.path.join(args.work, "Ddr3Bridge.v")
    _extract(args.hyper, "HyperRamBridge", hyper_v)
    _extract(args.ddr, "Ddr3Bridge", ddr_v)
    hyper_tb = os.path.join(args.work, "tb_hyper.v")
    ddr_tb = os.path.join(args.work, "tb_ddr.v")
    open(hyper_tb, "w", encoding="ascii").write(_hyper_tb())
    open(ddr_tb, "w", encoding="ascii").write(_ddr_tb())
    lut = os.path.join(ROOT, "sim", "LUT2.v")
    keep = os.path.join(ROOT, "gowin", "KeepBit.v")
    print(_run(args.work, [hyper_v, hyper_tb, lut, keep], "tb_hyper"), end="")
    print(_run(args.work, [ddr_v, ddr_tb], "tb_ddr"), end="")
    print(
        "bitmap windows 0xFFFE0000 and 0xFFFE8000 are decoded in the CPU "
        "and are not these ports"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
