//Copyright (C)2014-2024 Gowin Semiconductor Corporation.
//All rights reserved.
//File Title: IP file (SP, 64 x 32, bypass read, normal write, sync reset)
//GOWIN Version: V1.9.12.04 Standard
//Part Number: GW1NSR-LV4CQN48PC6/I5
//Device: GW1NSR-4C
//
// Ports match the Chisel BlackBox gcd.GowinSP / desiredName Gowin_SP.
// Two instances are inferred (MemoryController + RAMController).
//
// 32-bit SP addressing (UG285 / prim_sim.v):
//   AD[13:5] = word address
//   AD[4]    = unused
//   AD[3:0]  = byte-write enables (must be 1111 for a 32-bit store)

module Gowin_SP (dout, clk, oce, ce, reset, wre, ad, din);

output [31:0] dout;
input clk;
input oce;
input ce;
input reset;
input wre;
input [5:0] ad;
input [31:0] din;

wire gw_vcc;
wire gw_gnd;

assign gw_vcc = 1'b1;
assign gw_gnd = 1'b0;

SP sp_inst_0 (
    .DO(dout[31:0]),
    .CLK(clk),
    .OCE(oce),
    .CE(ce),
    .RESET(reset),
    .WRE(wre),
    .BLKSEL({gw_gnd,gw_gnd,gw_gnd}),
    .AD({gw_gnd,gw_gnd,gw_gnd,ad[5:0],gw_gnd,gw_vcc,gw_vcc,gw_vcc,gw_vcc}),
    .DI(din[31:0])
);

defparam sp_inst_0.READ_MODE = 1'b0;
defparam sp_inst_0.WRITE_MODE = 2'b00;
defparam sp_inst_0.BIT_WIDTH = 32;
defparam sp_inst_0.BLK_SEL = 3'b000;
defparam sp_inst_0.RESET_MODE = "SYNC";

endmodule
