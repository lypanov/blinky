MODULE AMemoryMappedToggle;

(* Module for memory-mapped light toggling *)

VAR light*, phase: INTEGER; (* light is the snooped word; phase is its source *)

(* Toggle the light state.
   The store is a constant 0 or 1 taken from phase, not from a
   read of light. A read of light that comes back odd makes
   1 - light even, and the pin snoop keeps the previous bit. *)
PROCEDURE Toggle*;
BEGIN
  IF phase = 0 THEN phase := 1; light := 1 ELSE phase := 0; light := 0 END
END Toggle;

BEGIN
  light := 0; phase := 0
END AMemoryMappedToggle. 