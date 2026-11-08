// Identity. A hard LUT so synthesis cannot prove a load's write flag is 0
// and delete the clear. INIT 8 is I0 & I1; both inputs are the same bit.
(* syn_hier = "hard" *)
module KeepBit (
  input  i,
  output o
);
  LUT2 u (
    .I0(i),
    .I1(i),
    .F(o)
  );
  defparam u.INIT = 4'h8;
endmodule
