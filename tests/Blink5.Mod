MODULE Blink5;
  IMPORT MMT := AMemoryMappedToggle, Kernel, SYSTEM;
  (*
    sim/link_inner.py places the arm sequence ahead of this loop. It runs once,
    before the wait, and stores one word at 7C0H. The word is
    0A11C0DE5H only when addresses 12, 16, 20, and 24 still hold MemLim,
    AllocPtr, the planted root, and the stack origin, 58 DIV 29 is 2 and
    the remainder in H is 0, and the sum of this placed code matches the
    word the linker stored at address 28. The LED pin stays dark otherwise.

    The loop stores the new light at -80 (0FFFFFFB0H). That is the one
    screen address: bit 0 of the word sets block (15, 11) and clears it.
    A board without that device decodes the store and drops it.

    Kernel.Time reads the counter at -64. The wait below is 1000 ms, so a
    toggle happens every second and a full blink is 0.500 Hz on both boards.
    The linker patches that 1000 for a short simulation.

    -60 is the book's switch word. Bit 0 is switch 0: 1 while the button
    is held, or while the Dock UART press latch is set. There are no
    interrupts. This loop polls the bit. While it is set the light stays
    where it is, and the deadline advances without a toggle, so a long
    hold does not queue a burst. Releasing it resumes the same wait.
  *)
  VAR last, now, wait, keys: INTEGER;
BEGIN
  last := Kernel.Time();
  wait := 1000;
  WHILE TRUE DO
    now := Kernel.Time();
    SYSTEM.GET(-60, keys);
    IF ODD(keys) THEN
      IF now - last >= wait THEN last := last + wait END
    ELSIF now - last >= wait THEN
      MMT.Toggle;
      SYSTEM.PUT(-80, MMT.light);
      last := last + wait
    END
  END
END Blink5.
