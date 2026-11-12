// Register snapshot for an F0 floating-point trap. One SP block on
// GW1NSR and GW2A. A 16-word array inferred from Verilog becomes logic
// on the Nano 4K, and that image is already at the logic limit.
//
// 32-bit SP addressing (UG285 / prim_sim.v), same as gowin/ip/gowin_sp.v:
//   AD[13:5] = word address. The 4-bit index sits in AD[8:5].
//   AD[4]    = unused
//   AD[3:0]  = byte-write enables (1111 for a 32-bit store)
// READ_MODE 0 is the bypass register: the word addressed this cycle
// is on DO after the clock. WRITE_MODE 00 does not update DO on a write.
// generated/FpSnap.v is the Verilator copy of that timing.

module FpSnap(
  input clk,
  input [3:0] addr,
  input we,
  input [31:0] wdata,
  output [31:0] rdata
);

wire gw_vcc;
wire gw_gnd;

assign gw_vcc = 1'b1;
assign gw_gnd = 1'b0;

SP u_snap (
    .DO(rdata),
    .CLK(clk),
    .OCE(gw_vcc),
    .CE(gw_vcc),
    .RESET(gw_gnd),
    .WRE(we),
    .BLKSEL({gw_gnd,gw_gnd,gw_gnd}),
    .AD({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,addr[3:0],gw_gnd,gw_vcc,gw_vcc,gw_vcc,gw_vcc}),
    .DI(wdata)
);

defparam u_snap.READ_MODE = 1'b0;
defparam u_snap.WRITE_MODE = 2'b00;
defparam u_snap.BIT_WIDTH = 32;
defparam u_snap.BLK_SEL = 3'b000;
defparam u_snap.RESET_MODE = "SYNC";

endmodule
