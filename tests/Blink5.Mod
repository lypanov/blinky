MODULE Blink5;
  IMPORT MMT := AMemoryMappedToggle, Kernel, Modules, Files, SYSTEM;
  (*
    This body fills a list, checks every record, then calls ArmHook.
    That call's immediate is where the arm sequence is entered. The
    sequence stores one word at 7C0H and returns. The word is
    0A11C0DE5H only when addresses 12, 16, 20, and 24 still hold
    MemLim, AllocPtr, the boot root, and the stack origin, 58 DIV 29
    is 2 and the remainder in H is 0, the two products match, the sum
    of this placed code matches the word stored at address 28, and
    kept is 1824. Modules loads Oberon, and Oberon loads this module.
    The LED pin stays dark otherwise.

    The loop draws the square, then stores the new light. The square is
    ordinary words in the bitmap. Bit 0 of a word is the left pixel.
    The 4K bitmap is at 0FFFE0000H, 256 bits a row, and the square is
    five rows of bits 11..15 at word 442 (0FFFE06E8H). The Dock bitmap
    is at 0FFFE8000H, 512 bits a row, and the square is ten rows of
    bits 22..31 at word 1764 (0FFFE9B90H). Both stores run on both
    boards. Each board keeps its own window and drops the other, so
    the lit box is the same 20 screen pixels at (300, 220).
    -84 (0FFFFFFACH) is the status register. Bit 8 selects the picture.
    This body stores 10BH once, before the file is opened, so the bitmap
    replaces the status blocks and the byte stays the inner core's 0BH.
    Until that store the blocks show the boot stage, bit 7 on the left.
    A board without that device decodes the store and drops it.

    Kernel.Time reads the counter at -64. The wait is the integer at the
    start of Blink.Rate, read once through Files.Old, then multiplied by
    FLOOR(0.5 * 2.0). That floor is 1, so the file still sets the rate.
    One thousand is a toggle every second and a full blink of 0.500 Hz.
    FLOOR(0.5 * 2000.0) is 1000. The four real operations are checked
    too: 1.5 + 2.5 is 4, 9.0 - 2.0 is 7, 0.5 * 8.0 is 4, and 15.0 / 3.0
    is 5. A miss stores the light off and stops before the arm word.
    The next four bytes of the file are the negation of the integer, so
    a second delay keeps the same disk checksum and the same arm word.
    A missing file, or a delay that is not positive, stores the light
    off and stops. The clock starts after that read. Opening the file
    takes longer than the delay, and a clock started earlier would
    queue a burst of toggles.

    The third time the light turns on, this loop halves the delay. The
    next edge is one half-delay later, and every edge after that stays
    there. The four edge gaps before that half are the file's original
    delay.

    -60 is the book's switch word. Bit 0 is switch 0: 1 while the button
    is held, or while the Dock UART press latch is set. There are no
    interrupts. This loop polls the bit. While it is set the light stays
    where it is, and the deadline advances without a toggle, so a long
    hold does not queue a burst. Releasing it resumes the same wait.

    MemLim is 28000H. The heap is the 65536 bytes from the stack origin
    18000H up to that limit. Files.Old of Oberon, AMemoryMappedToggle,
    this module, and Blink.Rate each take a 1280-byte buffer and a
    512-byte descriptor, 1792 bytes. Reading this module's second page
    reuses its one buffer. Those four opens take 7168 bytes. 1824
    records of 32 bytes fill the rest. head and node are global, so the
    collector follows them. kept counts the records that were linked.
    The arm word depends on that count. A limit one record lower finds
    no block for the last record, stores the light off, and stops
    before the arm word is stored.

    Every four on-edges, Collect marks from Modules.root and then scans,
    the way Oberon.GC does. A module whose pointer list is at 0 is skipped:
    Mark would load address 0, and this RAM powers up as ones. The same
    walk of the list runs again after Collect.
  *)
  TYPE Node = POINTER TO Rec;
    Rec = RECORD n: INTEGER; next: Node END;

  VAR last, now, wait, keys, n, due, half, thousand: INTEGER;
    node, head: Node;
    kept*: INTEGER;
    rate: Files.File;
    R: Files.Rider;
    sum, diff, prod, quot: REAL;

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

  PROCEDURE Square(on: INTEGER);
    VAR y, a: INTEGER;
  BEGIN
    (* 4K: five rows, stride 32, mask 0F800H at -129304. *)
    y := 0; a := -129304;
    WHILE y < 5 DO
      IF on = 1 THEN SYSTEM.PUT(a, 63488) ELSE SYSTEM.PUT(a, 0) END;
      a := a + 32; INC(y)
    END;
    (* Dock: ten rows, stride 64, mask 0FFC00000H at -91248. *)
    y := 0; a := -91248;
    WHILE y < 10 DO
      IF on = 1 THEN SYSTEM.PUT(a, -4194304) ELSE SYSTEM.PUT(a, 0) END;
      a := a + 64; INC(y)
    END
  END Square;

  PROCEDURE Dark;
  BEGIN
    (* An imported variable cannot be assigned. The store still hits the light. *)
    Square(0);
    SYSTEM.PUT(SYSTEM.ADR(MMT.light), 0);
    REPEAT UNTIL FALSE
  END Dark;

  PROCEDURE Check;
    VAR p: Node; i: INTEGER;
  BEGIN
    p := head; i := kept - 1;
    WHILE p # NIL DO
      IF p.n # i THEN Dark END;
      p := p.next; DEC(i)
    END;
    IF i # -1 THEN Dark END
  END Check;

  PROCEDURE ArmHook(k: INTEGER);
  BEGIN
  END ArmHook;

BEGIN
  SYSTEM.PUT(-84, 10BH);
  rate := Files.Old("Blink.Rate");
  IF rate = NIL THEN Dark END;
  Files.Set(R, rate, 0);
  Files.ReadInt(R, wait);
  IF wait <= 0 THEN Dark END;
  half := FLOOR(0.5 * 2.0);
  IF half # 1 THEN Dark END;
  thousand := FLOOR(0.5 * 2000.0);
  IF thousand # 1000 THEN Dark END;
  sum := 1.5 + 2.5;
  IF sum # 4.0 THEN Dark END;
  diff := 9.0 - 2.0;
  IF diff # 7.0 THEN Dark END;
  prod := 0.5 * 8.0;
  IF prod # 4.0 THEN Dark END;
  quot := 15.0 / 3.0;
  IF quot # 5.0 THEN Dark END;
  wait := wait * half;
  n := 0;
  due := 4;
  kept := 0; head := NIL;
  WHILE kept < 1824 DO
    NEW(node);
    IF node = NIL THEN Dark END;
    node.n := kept; node.next := head; head := node; INC(kept)
  END;
  Check;
  ArmHook(7E37H);
  last := Kernel.Time();
  WHILE TRUE DO
    now := Kernel.Time();
    SYSTEM.GET(-60, keys);
    IF ODD(keys) THEN
      IF now - last >= wait THEN last := last + wait END
    ELSIF now - last >= wait THEN
      IF MMT.light = 0 THEN Square(1) ELSE Square(0) END;
      MMT.Toggle;
      last := last + wait;
      IF MMT.light = 1 THEN
        INC(n);
        IF n = 3 THEN wait := wait DIV 2 END;
        DEC(due);
        IF due = 0 THEN Collect; Check; due := 4 END
      END
    END
  END
END Blink5.
