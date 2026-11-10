MODULE Blink5;
  IMPORT MMT := AMemoryMappedToggle, Kernel, Modules, SYSTEM;
  (*
    sim/link_inner.py places the arm sequence ahead of this loop. It runs once,
    before the wait, and stores one word at 7C0H. The word is
    0A11C0DE5H only when addresses 12, 16, 20, and 24 still hold MemLim,
    AllocPtr, the planted root, and the stack origin, 58 DIV 29 is 2 and
    the remainder in H is 0, the two products match, and the sum of this
    placed code matches the word the linker stored at address 28. The LED
    pin stays dark otherwise.

    The loop stores the new light at -80 (0FFFFFFB0H). That is the one
    screen address: bit 0 of the word sets block (15, 11) and clears it.
    A board without that device decodes the store and drops it. The Dock
    counts the stores whose bit is 1.

    Kernel.Time reads the counter at -64. The wait below is 1000 ms, so a
    toggle happens every second and a full blink is 0.500 Hz on both boards.
    The linker patches that 1000 for a short simulation.

    -60 is the book's switch word. Bit 0 is switch 0: 1 while the button
    is held, or while the Dock UART press latch is set. There are no
    interrupts. This loop polls the bit. While it is set the light stays
    where it is, and the deadline advances without a toggle, so a long
    hold does not queue a burst. Releasing it resumes the same wait.

    Each on-edge allocates one record and drops it. head stays reachable,
    and its next field points at itself, so the collector follows one real
    pointer offset from the type descriptor the loader placed. MemLim is
    0CF00H. The heap is the 3840 bytes from the stack origin 0C000H up to
    that limit. The two open files take 3584 of those bytes. Reading this
    module's second page reuses the one buffer, so it takes no more.
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

  VAR last, now, wait, keys, n, due: INTEGER;
    node, head: Node;

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
  last := Kernel.Time();
  wait := 1000;
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
        DEC(due);
        IF due = 0 THEN Collect; due := 4 END
      END
    END
  END
END Blink5.
