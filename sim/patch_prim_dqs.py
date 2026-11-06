#!/usr/bin/env python3
"""Patch gw2a prim_sim so the DQS delay is one transport delay per strobe.

The vendor DQS model is a cascade of 255 inertial taps, 0.025 ns each
(module timescale 1 ns). Tap N is N * 0.025 ns. Icarus schedules every
tap on every edge, and the Micron bench then takes minutes per
microsecond. One procedural transport delay of N * 0.025 ns is the same
strobe while a step is held. The controller settles a new step for 16
pclk before it uses it.

The patched file is a build product. The vendor prim_sim.v is not
modified.
"""

import sys
from pathlib import Path

OLD_WIRES = "wire [255:0] dqsw270_dly_in,dqsr90_dly_in,dqsw0_dly_in;\n"

OLD_CHAIN = """/*********** DQSW/DQSR gen_delay begin *************/
assign dqsw0_dly_in[0] = fclk_in;
assign dqsw270_dly_in[0] =  fclk_in;
assign dqsr90_dly_in[0] = dqs_r_clean;
generate 
   genvar i;
    for(i=1;i<256;i=i+1) begin: gen_delay
      assign #0.025 dqsw0_dly_in[i] = dqsw0_dly_in[i-1];
      assign #0.025 dqsw270_dly_in[i] = dqsw270_dly_in[i-1];
      assign #0.025 dqsr90_dly_in[i] = dqsr90_dly_in[i-1];
    end
endgenerate

wire DQSW90;
assign DQSW0 = (DQS_MODE == "X1") ? fclk_in : dqsw0_dly_in[WSTEP];
assign DQSW90 = (wstep_reg == 0) ? fclk_in : dqsw270_dly_in[wstep_reg];
assign DQSW270 = ~DQSW90;
assign DQSR90 = (rstep_reg == 0) ? dqs_r_clean : dqsr90_dly_in[rstep_reg];
/************* DQSW/DQSR gen_delay end ************/
"""

def _taps(name: str, n: int, src: str) -> str:
    """Constant transport delays. N*0.025 ns races a CK edge in the
    Micron latching check; 1 ps early is the delay that passed at
    write-level code 26. A variable delay expression does not."""
    lines = [f"reg [{n-1}:0] {name};", f"always @({src}) begin"]
    lines.append(f"    {name}[0] <= {src};")
    for i in range(1, n):
        lines.append(f"    {name}[{i}] <= #{i * 0.025 - 0.001:.3f} {src};")
    lines.append("end")
    return "\n".join(lines)


NEW_CHAIN = (
    "/*********** DQSW/DQSR constant transport taps *************/\n"
    "// Vendor tap N = N * 0.025 ns. These are the same delays, 1 ps\n"
    "// early, for every code the write-eye walk can select.\n"
    + _taps("ftap", 64, "fclk_in")
    + "\n"
    + _taps("wtap", 96, "fclk_in")
    + "\n"
    + _taps("rtap", 40, "dqs_r_clean")
    + """
wire DQSW90;
assign DQSW0 = (DQS_MODE == "X1" || WSTEP == 8'd0) ? fclk_in :
               (WSTEP < 64) ? ftap[WSTEP] : 1'bx;
assign DQSW90 = (wstep_reg == 8'd0) ? fclk_in :
                (wstep_reg < 96) ? wtap[wstep_reg] : 1'bx;
assign DQSW270 = ~DQSW90;
assign DQSR90 = (rstep_reg == 8'd0) ? dqs_r_clean :
                (rstep_reg < 40) ? rtap[rstep_reg] : 1'bx;
/************* DQSW/DQSR gen_delay end ************/
"""
)


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: patch_prim_dqs.py SRC DEST", file=sys.stderr)
        sys.exit(2)
    src = Path(sys.argv[1]).read_text()
    if OLD_WIRES not in src or OLD_CHAIN not in src:
        print("FAIL prim_sim DQS delay chain not found; vendor file changed", file=sys.stderr)
        sys.exit(1)
    out = src.replace(OLD_WIRES, "", 1).replace(OLD_CHAIN, NEW_CHAIN, 1)
    dest = Path(sys.argv[2])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out)
    print(f"prim_dqs {dest}")


if __name__ == "__main__":
    main()
