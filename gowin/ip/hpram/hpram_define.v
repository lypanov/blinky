// Plain defines for the installed HyperRAM IP (IPUG944, HPRAM_TOP.v).
// Included ahead of /opt/gowin-eda-ide/ipcore/HYPERRAM/data so these
// replace the generator output. SIM is deliberately not defined:
// Accelerate Simulation must be off for the board.
`define module_name_hpram HyperRAM_Memory_Interface_Top
`define W956_PSRAM
`define DEVICE1N
`define CLK_DIFF
`define burst16
`define EBR_BASED
