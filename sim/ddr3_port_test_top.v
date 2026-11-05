// Sim harness: ddr3_port_test against the behavioural command port.
module ddr3_port_test_top (
  input  clk,
  input  rst_n,
  output done,
  output passed,
  output failed,
  output [1:0] edge_sel
);
  wire        rd, wr, refresh, data_ready, busy, calib;
  wire [25:0] addr;
  wire [15:0] din, dout, dout_model;

  ddr3_port_test #(.WORDS(64)) u_test (
    .clk(clk),
    .resetn(rst_n),
    .calib(calib),
    .rd(rd),
    .wr(wr),
    .refresh(refresh),
    .addr(addr),
    .din(din),
    .dout(dout),
    .data_ready(data_ready),
    .busy(busy),
    .passed(passed),
    .failed(failed),
    .done(done),
    .edge_sel(edge_sel),
    .noready(),
    .samp0(),
    .samp1(),
    .samp2()
  );

  Ddr3UserModel u_model (
    .clk(clk),
    .rst_n(rst_n),
    .rd(rd),
    .wr(wr),
    .refresh(refresh),
    .addr(addr),
    .din(din),
    .dout(dout_model),
    .data_ready(data_ready),
    .busy(busy),
    .calib(calib)
  );

  assign dout = dout_model;
endmodule
