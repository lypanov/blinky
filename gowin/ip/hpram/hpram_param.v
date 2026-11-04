// User parameters for GW1NSR-4C embedded W956x8MKY (8 MB, x8).
// Memory_Clock is the PLL output. The IP's clk_out is that clock / 2
// and is the CPU clock. 54 MHz is inside the 50–200 MHz W956 range and
// at or below 83 MHz, where initial latency 3 is legal (IPUG944).
parameter Memory_Clock = 54;
parameter PSRAM_WIDTH = 8;
parameter DQ_WIDTH = 8;
parameter ADDR_WIDTH = 22;
parameter Burst_Length = "16_Bytes";
parameter burst_num = 4;
parameter Fixed_Latency_Enable = "Fixed";
parameter Initial_Latency = 3;
parameter Drive_Strength = "34";
parameter Deep_Power_Down = "OFF";
parameter Hybrid_Sleep_Mode = "OFF";
parameter Refresh_Rate = "normal";
parameter PASR = "full";
