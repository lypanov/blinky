MODULE Blink5;
  IMPORT MMT := AMemoryMappedToggle, SYSTEM;
  (*
    sim/link_inner.py places the arm sequence ahead of this loop. It runs once,
    before the delay loop, and stores one word at 7C0H. The word is
    0A11C0DE5H only when addresses 12, 16, 20, and 24 still hold MemLim,
    AllocPtr, the planted root, and the stack origin, 58 DIV 29 is 2 and
    the remainder in H is 0, and the sum of this placed code matches the
    word the linker stored at address 28. The LED pin stays dark otherwise.

    The loop stores the new light at -80 (0FFFFFFB0H). That is the one
    screen address: bit 0 of the word sets block (15, 11) and clears it.
    A board without that device decodes the store and drops it.
  *)
  VAR counter, maxIterations: INTEGER;
BEGIN
  counter := 0;
  maxIterations := 65536;
  WHILE TRUE DO
    INC(counter);
    IF counter >= maxIterations THEN
      MMT.Toggle;
      SYSTEM.PUT(-80, MMT.light);
      counter := 0
    END
  END
END Blink5.
