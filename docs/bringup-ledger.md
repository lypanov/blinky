# Bring-up ledger

Ranked cuts on the Nano 4K. Three passes (the Logger, the register-file read mux, and the shifter) produced five options. This is that ranking.

CLS is the scarce resource: about 2173/2304 used (95%), 131 free. The figures are from the `modules_n262144` synthesis tree and netlist.

The Logger, one register-file cut, and one shifter are different logic and can be stacked. The two register-file options are one mux, and the two shifter options are one barrel. Picking both of a pair counts that logic twice.

1. Omit the Logger on the 4K. Largest easy cut that leaves both blink laws alone: about 175 CLS, and 209 LUT plus 68 ALU (about 277 logic cells). Free CLS goes from 131 to about 306. Placed logic goes to about 80%. Easy. `103*N+142` and `576*N+788` stay as they are. The Dock training UART is a different block and stays. The trap is a shared generated wrapper: drop the Logger on the 4K elaboration only, and leave the Dock UART in place.

2. Cut the register file to a same-cycle 2-port read. The other easy cut that leaves the blink laws alone. All 16 registers stay, and the compiler does not change. About 128 CLS and 256 LUT3 (about 480 cells). Easy. No instruction reads three registers. The 27 MHz path still runs through a port that remains.

3. Time-multiplex a 1-port register file. This frees the most CLS and sits behind the easy cuts. About 256 CLS and 512 LUT3 (about 960 cells). Medium, because the pipeline has to hold PC and chainFix until the read commits. The skip loop becomes about `105*N+146`. The full blink is still about 0.49 Hz.

4. Replace the 5-stage barrel with a 1-bit-per-clock shifter. Smaller CLS return than the 1-port file, same kind of effort, and the blink slope is unchanged. About 110–150 CLS and 250–280 LUT (about 95% CLS down to about 89% if that CLS comes back). Medium. The 4K netlist elaborates only the slow shifter. chainFix has to treat a pending shift like a memory stall. The delay loop does not shift.

5. A 4-bit-per-clock shifter is last. The same medium change, for less area: about 90–120 CLS and 190–220 LUT. The blink slope is unchanged.

Among the easy cuts that keep both blink laws, omitting the Logger frees the most CLS.
