MODULE Blink5;
  IMPORT MMT := AMemoryMappedToggle, Kernel, Modules, Files, SYSTEM;
  (*
    The arm sequence is placed ahead of this loop. It runs once, before
    the wait, and stores one word at 7C0H. The word is 0A11C0DE5H only
    when addresses 12, 16, 20, and 24 still hold MemLim, AllocPtr, the
    boot root, and the stack origin, 58 DIV 29 is 2 and the remainder in
    H is 0, the two products match, and the sum of this placed code
    matches the word stored at address 28. Modules loads Oberon, and
    Oberon loads this module. The LED pin stays dark otherwise.

    The loop stores the new light at -80 (0FFFFFFB0H). That is the one
    screen address: bit 0 of the word sets block (15, 11) and clears it.
    A board without that device decodes the store and drops it. The Dock
    counts the stores whose bit is 1.

    Kernel.Time reads the counter at -64. The wait is the integer at the
    start of Blink.Rate, read once through Files.Old. One thousand is a
    toggle every second and a full blink of 0.500 Hz. The next four bytes
    are the negation of that integer, so a second delay keeps the same
    disk checksum and the same arm word. A missing file, or a delay that
    is not positive, stores the light off and stops. The clock starts
    after that read. Opening the file takes longer than the delay, and
    a clock started earlier would queue a burst of toggles.

    The third time the light turns on, this loop writes half that delay
    and the negation of the half, closes the file, and reads it back.
    Close has dropped the cached page, so the read is Kernel.GetSector
    of the page PutSector kept in RAM. The flash is unchanged. The word
    read back has to be the half that was written. The next edge is one
    half-delay later, and every edge after that stays there. The four
    edge gaps before that half are the file's original delay. A wrong
    word stores the light off and stops.

    -60 is the book's switch word. Bit 0 is switch 0: 1 while the button
    is held, or while the Dock UART press latch is set. There are no
    interrupts. This loop polls the bit. While it is set the light stays
    where it is, and the deadline advances without a toggle, so a long
    hold does not queue a burst. Releasing it resumes the same wait.

    Each on-edge allocates one record and drops it. head stays reachable,
    and its next field points at itself, so the collector follows one real
    pointer offset from the type descriptor the loader placed. MemLim is
    19D00H. The heap is the 7424 bytes from the stack origin 18000H up to
    that limit. Files.Old of Oberon, AMemoryMappedToggle, this module, and
    Blink.Rate each take a 1280-byte buffer and a 512-byte descriptor,
    1792 bytes. Reading this module's second page reuses its one buffer.
    Eight 32-byte blocks remain. head takes one. Seven on-edges succeed.
    The eighth stores the light, finds no block, forces the light off,
    and stops. The Dock counter then reads 0008.

    Every four on-edges, Collect marks from Modules.root and then scans,
    the way Oberon.GC does. A module whose pointer list is at 0 is skipped:
    Mark would load address 0, and this RAM powers up as ones. With the
    collector in place, the eighth on-edge still finds a block.
  *)
  TYPE Node = POINTER TO Rec;
    Rec = RECORD n: INTEGER; next: Node END;

  VAR last, now, wait, old, keys, n, due: INTEGER;
    node, head: Node;
    rate: Files.File;
    R: Files.Rider;

  PROCEDURE Collect;
    VAR m: Modules.Module;
  BEGIN
    m := Modules.root;
    WHILE m # NIL DO
      IF (m.name[0] # 0X) & (m.ptr # 0) THEN Kernel.Mark(m.ptr) END;
      m := m.next
    END;
    Kernel.Scan
  END Collect;

  PROCEDURE Dark;
  BEGIN
    (* An imported variable cannot be assigned. The store still hits the light. *)
    SYSTEM.PUT(SYSTEM.ADR(MMT.light), 0);
    SYSTEM.PUT(-80, 0);
    REPEAT UNTIL FALSE
  END Dark;

BEGIN
  rate := Files.Old("Blink.Rate");
  IF rate = NIL THEN Dark END;
  Files.Set(R, rate, 0);
  Files.ReadInt(R, wait);
  IF wait <= 0 THEN Dark END;
  last := Kernel.Time();
  n := 0;
  due := 4;
  NEW(head);
  IF head = NIL THEN Dark END;
  head.n := 0;
  head.next := head;
  WHILE TRUE DO
    now := Kernel.Time();
    SYSTEM.GET(-60, keys);
    IF ODD(keys) THEN
      IF now - last >= wait THEN last := last + wait END
    ELSIF now - last >= wait THEN
      MMT.Toggle;
      SYSTEM.PUT(-80, MMT.light);
      last := last + wait;
      IF MMT.light = 1 THEN
        NEW(node);
        IF node = NIL THEN Dark END;
        node.n := n;
        node.next := NIL;
        node := head;
        INC(n);
        IF n = 3 THEN
          old := wait;
          Files.Set(R, rate, 0);
          Files.WriteInt(R, old DIV 2);
          Files.WriteInt(R, -(old DIV 2));
          Files.Close(rate);
          rate := Files.Old("Blink.Rate");
          IF rate = NIL THEN Dark END;
          Files.Set(R, rate, 0);
          Files.ReadInt(R, wait);
          IF wait # old DIV 2 THEN Dark END
        END;
        DEC(due);
        IF due = 0 THEN Collect; due := 4 END
      END
    END
  END
END Blink5.
