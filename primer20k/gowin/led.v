// Sipeed Tang Primer 20K Dock blinky.
// Logic is the wiki Dock LED example (examples/led.html): 27 MHz clock,
// COUNT_VALUE ticks, then flip. Wiki uses L14 only; this fans the same
// toggle to all six user LEDs (L14 plus the other five) so the webcam can lock onto whichever is
// in frame. LEDs are active-low; the wiki does not invert, so neither
// do we. Frequency is independent of polarity.
//
// Default COUNT_VALUE = 13_499_999 -> 0.5 s half-period -> 1 Hz.
// Override with `define COUNT_VALUE before including this file.

module led (
    input  Clock,
    output IO_voltage,
    output [4:0] led
);

`ifndef COUNT_VALUE
`define COUNT_VALUE 13_499_999
`endif

parameter count_value = `COUNT_VALUE;

reg [23:0] count_value_reg  = 24'b0;
reg        count_value_flag = 1'b0;

always @(posedge Clock) begin
    if (count_value_reg <= count_value) begin
        count_value_reg  <= count_value_reg + 1'b1;
        count_value_flag <= 1'b0;
    end else begin
        count_value_reg  <= 23'b0;
        count_value_flag <= 1'b1;
    end
end

reg IO_voltage_reg = 1'b0;

always @(posedge Clock) begin
    if (count_value_flag)
        IO_voltage_reg <= ~IO_voltage_reg;
    else
        IO_voltage_reg <= IO_voltage_reg;
end

assign IO_voltage = IO_voltage_reg;
assign led        = {5{IO_voltage_reg}};

endmodule
