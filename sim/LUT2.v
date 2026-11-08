// Simulation model of the Gowin LUT2 primitive used by KeepBit.
module LUT2 (
  input I0,
  input I1,
  output F
);
  parameter [3:0] INIT = 4'h0;
  assign F = INIT[{I1, I0}];
endmodule
