MODULE Oberon;
  IMPORT Modules, SYSTEM;
  VAR M: Modules.Module;
BEGIN
  (* Stage 11. Bit 8 stays clear, so the blocks keep this code until
     Blink5 stores it with the mode bit set. *)
  SYSTEM.PUT(-84, 0BH);
  Modules.Load("Blink5", M)
END Oberon.
