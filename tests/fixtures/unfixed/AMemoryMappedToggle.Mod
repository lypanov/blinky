MODULE AMemoryMappedToggle;

(* Module for memory-mapped light toggling *)

VAR light*: INTEGER; (* Exported variable for light state *)

(* Toggle the light state *)
PROCEDURE Toggle*;
BEGIN
  light := 1 - light; (* toggle light, memory writes are intercepted *)
END Toggle;

BEGIN
  light := 0; (* Initialize light to off *)
END AMemoryMappedToggle.
