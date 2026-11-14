MODULE Blink;
  IMPORT Files, Fonts, Texts, Display, MMT := AMemoryMappedToggle, Input, Kernel, Modules, Oberon, SYSTEM;
  (* The 4K square is five bitmap pixels at (75, 55). The letter A is
     at (81, 55), in the same words, one bitmap pixel to the right of
     the square so screen x 320 stays dark. The Dock build replaces
     these two lines with the square at 150, 110, 10, 10 and the letter
     at 161, 110. Both squares are the 20-pixel box at screen (300, 220). *)
  CONST sqX = 75; sqY = 55; sqW = 5; sqH = 5;
    mkX = 81; mkY = 55;
    tx = 64; ty = 40;
    lnX = 4; lnY = 8;
    tnX = 4; tnY = 100; tnW = 40; tnH = 8;
    slackRecs = 33; (*the full heap's free records; the short limit has one fewer*)
  (*
    This body fills a list, checks every record, then calls ArmHook.
    That call's immediate is where the arm sequence is entered. The
    sequence stores one word at 7C0H and returns. The word is
    0A11C0DE5H only when addresses 12, 16, 20, and 24 still hold
    MemLim, AllocPtr, the boot root, and the stack origin, 58 DIV 29
    is 2 and the remainder in H is 0, the two products match, the sum
    of this placed code matches the word stored at address 28, and
    kept is 1191. Modules loads Oberon. Oberon.Call starts this
    module by the command Blink.Run. The LED pin stays dark otherwise.

    The loop draws the square, the letter, and the count, then stores
    the new light. Texts.WriteInt writes the count into a text. The
    line is drawn with this font, one glyph at a time. Display is the
    book's module. ReplConst paints the rectangle. CopyPattern paints
    into words the square may already own, so the load has to return
    what was stored. The font file is bottom-row first and this
    bitmap's Y increases downward, so the rows are reversed first.
    This board's
    width, height and bitmap address are its constants. The 4K bitmap
    is at 0FFFE0000H, 256 bits a row, and the square is five rows of
    bits 11..15 at word 442 (0FFFE06E8H). The Dock bitmap is at
    0FFFE8000H, 512 bits a row, and the square is ten rows of bits
    22..31 at word 1764 (0FFFE9B90H). Each image keeps one window.
    -84 (0FFFFFFACH) is the status register. Bit 8 selects the picture.
    Run stores 10BH once, before the file is opened, so the bitmap
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

    A trap after the font is loaded prints the book's one line. The
    text is the one System.Trap writes: the position, the trap number,
    the module, and the address. The line is drawn with this font.
    Kernel keeps the status code until Run has installed that handler.
    A trap before the font is loaded still stores 80H plus the number.
    NEW and the floating-point traps chain back to Kernel. The arm
    word is not stored, so the LED stays dark.

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
    18000H up to that limit. Files.Old of Oberon, Fonts, the font,
    Display, AMemoryMappedToggle, this module, Texts, Input, and
    Blink.Rate, plus the trailer file and the writer file, are eleven
    opens. Each takes a 1280-byte buffer and a 512-byte descriptor,
    19712 bytes. Reading a later page of a file reuses its one buffer.
    Fonts allocates two blocks of 3072 bytes. The text, the two buffers
    and the three pieces are 288 bytes, and 1280 bytes stay free so the
    count can be written until Collect. 1191 records of 32 bytes fill
    the rest. The heap has 33 records free after that list on the full
    limit, and 32 when MemLim is one record lower. Those 33 are held
    while the list is built, then released. head, node and spare are
    global, so the
    collector follows them. kept counts the records that were linked.
    The arm word depends on that count. A limit one record lower finds
    no block for the last record, stores the light off, and stops
    before the arm word is stored.

    Input is the book's module. SetMouseLimits, Mouse, and Available
    run before the list is built. -40 reads 0 and -36 reads 0: no key
    is ready, and the mouse sits at the origin with the buttons up.
    Available is 0, the key set is empty, and both coordinates are 0.
    The arm word is stored only after that answer. An image where -40
    reads ones makes Available report a key and Mouse report the three
    buttons at the far corner. This loop then stores the light off and
    halts. The arm word is not stored, so the LED stays dark.

    Run returns after Install. Oberon.Loop is the book's loop: each
    turn polls the mouse and the keyboard, and with neither pending it
    calls the next task whose time has come. The blink task's period
    is the file's delay. The loop sets the next deadline before the
    handler runs, so a held button skips the toggle and does not queue
    a burst. The period is halved on the off-edge after the second
    on, which is the gap after the third on. Oberon.Turns counts the
    loop's turns. The number is drawn in an 8-character field, and it
    stays up while the square goes dark. A second task that never
    returns, once the light has come on twice, stops the loop. The
    LED stays on.

    Every four on-edges, Collect marks from Modules.root and then scans,
    the way Oberon.GC does. A module whose pointer list is at 0 is skipped:
    Mark would load address 0, and this RAM powers up as ones. The same
    walk of the list runs again after Collect.
  *)
  TYPE Node = POINTER TO Rec;
    Rec = RECORD n: INTEGER; next: Node END;

  VAR last, now, wait, keys, n, due, half, thousand: INTEGER;
    hang: INTEGER;
    task, stuck: Oberon.Task;
    mx, my: INTEGER;
    mkeys: SET;
    node, head, spare: Node;
    kept*: INTEGER;
    rate: Files.File;
    R: Files.Rider;
    sum, diff, prod, quot: REAL;
    line: Texts.Text;
    W: Texts.Writer;
    junk: Texts.Buffer;
    reporting: BOOLEAN;

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
  BEGIN
    IF on = 1 THEN
      Display.ReplConst(Display.white, sqX, sqY, sqW, sqH, Display.replace)
    ELSE
      Display.ReplConst(Display.black, sqX, sqY, sqW, sqH, Display.replace)
    END
  END Square;

  PROCEDURE Dark;
  BEGIN
    (* An imported variable cannot be assigned. The store still hits the light. *)
    Square(0);
    SYSTEM.PUT(SYSTEM.ADR(MMT.light), 0);
    REPEAT UNTIL FALSE
  END Dark;

  PROCEDURE Note(T: Texts.Text; op: INTEGER; beg, en: LONGINT);
  BEGIN
  END Note;

  PROCEDURE PaintChar(on, px, py, w, h, pat: INTEGER);
    VAR row, nb, k, src, dst: INTEGER;
      b: BYTE;
      buf: ARRAY 16 OF BYTE;
  BEGIN
    nb := (w + 7) DIV 8;
    SYSTEM.PUT(SYSTEM.ADR(buf), CHR(w));
    SYSTEM.PUT(SYSTEM.ADR(buf) + 1, CHR(h));
    dst := SYSTEM.ADR(buf) + 2;
    row := 0;
    WHILE row < h DO
      src := pat + 2 + (h - 1 - row) * nb;
      k := 0;
      WHILE k < nb DO
        SYSTEM.GET(src, b); SYSTEM.PUT(dst, b); INC(src); INC(dst); INC(k)
      END;
      INC(row)
    END;
    (* Paint and invert are different instruction streams, and the
       off edge has to take as long as the on edge. Invert on a black
       background is the same picture as paint, and the next invert
       clears it. *)
    IF on >= 0 THEN
      Display.CopyPattern(Display.white, SYSTEM.ADR(buf), px, py, Display.invert)
    ELSE
      Display.CopyPattern(Display.white, SYSTEM.ADR(buf), px, py, Display.paint)
    END
  END PaintChar;

  (* Eight digits every edge, leading zeros included. GetPat and
     PaintChar take the same path for every digit of this font, and
     the field is erased first, so the on and off edges spend the
     same time here. The digits stay while the square is inverted off.
     Texts is not used: WriteInt of this field did not fit in 8 ms. *)
  PROCEDURE DrawTurns;
    VAR v, d, dig, dx, x, y, w, h, pat, pen: INTEGER;
  BEGIN
    Display.ReplConst(Display.black, tnX, tnY, tnW, tnH, Display.replace);
    v := Oberon.Turns; d := 10000000; pen := tnX;
    WHILE d > 0 DO
      dig := v DIV d; v := v MOD d;
      Fonts.GetPat(Fonts.Default, CHR(dig + ORD(30X)), dx, x, y, w, h, pat);
      IF (w < 1) OR (w > 8) OR (h < 1) OR (h > 8) THEN Dark END;
      PaintChar(-1, pen + x, tnY + y, w, h, pat);
      pen := pen + dx; d := d DIV 10
    END
  END DrawTurns;

  PROCEDURE Show(on: INTEGER);
    VAR Rdr: Texts.Reader;
      ch: CHAR;
      dx, x, y, w, h, pat, pen, i: INTEGER;
  BEGIN
    IF on = 1 THEN
      (* On the Dock the lit Show is about 2000 bridge clocks shorter
         than the dark one. Two of these steps put that difference
         back inside the poll slack on both boards. *)
      i := 0;
      WHILE i < 2 DO INC(i) END
    END;
    Display.ReplConst(Display.white, sqX, sqY, sqW, sqH, Display.invert);
    Fonts.GetPat(Fonts.Default, 41X, dx, x, y, w, h, pat);
    IF (w < 1) OR (w > 8) OR (h < 1) OR (h > 8) THEN Dark END;
    PaintChar(on, mkX + x, mkY + y, w, h, pat);
    Texts.WriteInt(W, n, 1);
    Texts.Append(line, W.buf);
    Texts.OpenReader(Rdr, line, 0);
    pen := tx;
    Texts.Read(Rdr, ch);
    WHILE ~Rdr.eot DO
      Fonts.GetPat(Fonts.Default, ch, dx, x, y, w, h, pat);
      IF (w < 0) OR (w > 8) OR (h < 0) OR (h > 8) THEN Dark END;
      IF (w > 0) & (h > 0) THEN PaintChar(on, pen + x, ty + y, w, h, pat) END;
      pen := pen + dx;
      Texts.Read(Rdr, ch)
    END;
    IF line.len # 0 THEN
      (* Delete keeps this buffer's header. Opening a new one allocates,
         and that block comes off a free list whose shape changes from
         edge to edge, which moved the off edge past the poll slack. *)
      Texts.Delete(line, 0, line.len, junk)
    END
  END Show;

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

  PROCEDURE Tick;
  BEGIN
    SYSTEM.GET(-60, keys);
    IF ~ODD(keys) THEN
      DrawTurns;
      IF MMT.light = 0 THEN INC(n); Show(1) ELSE Show(0) END;
      SYSTEM.LDREG(5, 0);
      SYSTEM.LDREG(9, 0);
      MMT.Toggle;
      IF MMT.light = 1 THEN
        DEC(due);
        IF due = 0 THEN Collect; Check; due := 4 END
      ELSIF n = 2 THEN
        task.period := task.period DIV 2
      END
    END
  END Tick;

  PROCEDURE Stick;
  BEGIN
    IF n >= 2 THEN REPEAT UNTIL FALSE END
  END Stick;

  PROCEDURE ArmHook(k: INTEGER);
  BEGIN
  END ArmHook;

  PROCEDURE DrawChar(px, py, w, h, pat: INTEGER);
    VAR row, nb, k, src, dst: INTEGER;
      b: BYTE;
      buf: ARRAY 32 OF BYTE;
  BEGIN
    IF (w >= 1) & (w <= 16) & (h >= 1) & (h <= 16) THEN
    nb := (w + 7) DIV 8;
    SYSTEM.PUT(SYSTEM.ADR(buf), CHR(w));
    SYSTEM.PUT(SYSTEM.ADR(buf) + 1, CHR(h));
    dst := SYSTEM.ADR(buf) + 2;
    row := 0;
    WHILE row < h DO
      src := pat + 2 + (h - 1 - row) * nb;
      k := 0;
      WHILE k < nb DO
        SYSTEM.GET(src, b); SYSTEM.PUT(dst, b); INC(src); INC(dst); INC(k)
      END;
      INC(row)
    END;
    Display.CopyPattern(Display.white, SYSTEM.ADR(buf), px, py, Display.invert)
    END
  END DrawChar;

  (* System.Trap's line, then a halt. The vector stays Kernel.Trap.
     NEW and floating point never arrive here. A second trap, or a
     missing font, stores 80H plus the number and stops. *)
  PROCEDURE Report(n, pos, lnk: INTEGER);
    VAR mod: Modules.Module;
      Rdr: Texts.Reader;
      ch: CHAR;
      dx, x, y, w, h, pat, pen: INTEGER;
      T: Texts.Text;
      TW: Texts.Writer;
  BEGIN
    IF reporting OR (Fonts.Default = NIL) THEN
      SYSTEM.PUT(-84, 80H + n); LED(n + 192); REPEAT UNTIL FALSE
    END;
    reporting := TRUE;
    NEW(T);
    IF T # NIL THEN
      Texts.Open(T, "");
      T.notify := Note;
      Texts.OpenWriter(TW);
      IF TW.buf # NIL THEN
        Texts.WriteLn(TW);
        Texts.WriteString(TW, "  pos ");
        Texts.WriteInt(TW, pos, 4);
        Texts.WriteString(TW, "  TRAP");
        Texts.WriteInt(TW, n, 4);
        mod := Modules.root;
        WHILE (mod # NIL) & ((lnk < mod.code) OR (lnk >= mod.imp)) DO mod := mod.next END;
        IF mod # NIL THEN
          Texts.WriteString(TW, " in "); Texts.WriteString(TW, mod.name)
        END;
        Texts.WriteString(TW, " at");
        Texts.WriteHex(TW, lnk);
        Texts.WriteLn(TW);
        Texts.Append(T, TW.buf);
        (* Bitmap pixels stay dark until this bitstream's arm word.
           The blink loop does not run, so the LED stays dark. *)
        SYSTEM.PUT(7C0H, 222FE47DH);
        Texts.OpenReader(Rdr, T, 0);
        pen := lnX;
        Texts.Read(Rdr, ch);
        WHILE ~Rdr.eot DO
          Fonts.GetPat(Fonts.Default, ch, dx, x, y, w, h, pat);
          IF (w > 0) & (h > 0) THEN DrawChar(pen + x, lnY + y, w, h, pat) END;
          pen := pen + dx;
          Texts.Read(Rdr, ch)
        END;
        SYSTEM.PUT(-84, 10BH);
        REPEAT UNTIL FALSE
      END
    END;
    SYSTEM.PUT(-84, 80H + n); LED(n + 192); REPEAT UNTIL FALSE
  END Report;

  PROCEDURE InstallGate;
  BEGIN Kernel.SetHandler(Report)
  END InstallGate;

  PROCEDURE Run*;
    VAR dx, x, y, w, h, pat: INTEGER;
  BEGIN
  Fonts.GetPat(Fonts.Default, 41X, dx, x, y, w, h, pat);
  IF (Fonts.Default = NIL) OR (w < 1) OR (h < 1) THEN Dark END;
  InstallGate;
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
  Input.SetMouseLimits(1024, 768);
  Input.Mouse(mkeys, mx, my);
  IF (Input.Available() # 0) OR (mkeys # {}) OR (mx # 0) OR (my # 0) THEN Dark END;
  wait := wait * half;
  NEW(line);
  IF line = NIL THEN Dark END;
  Texts.Open(line, "");
  line.notify := Note;
  NEW(junk);
  IF junk = NIL THEN Dark END;
  Texts.OpenBuf(junk);
  Texts.OpenWriter(W);
  IF W.buf = NIL THEN Dark END;
  n := 0;
  due := 4;
  kept := 0; head := NIL; spare := NIL;
  half := 0;
  WHILE half < slackRecs DO
    NEW(node);
    IF node = NIL THEN Dark END;
    node.next := spare; spare := node; INC(half)
  END;
  WHILE kept < 1191 DO
    NEW(node);
    IF node = NIL THEN Dark END;
    node.n := kept; node.next := head; head := node; INC(kept)
  END;
  spare := NIL;
  Collect;
  Check;
  ArmHook(7E37H);
  last := Kernel.Time();
  now := last;
  hang := 0;
  task := Oberon.NewTask(Tick, wait);
  IF task = NIL THEN Dark END;
  Oberon.Install(task);
  IF hang # 0 THEN
    stuck := Oberon.NewTask(Stick, 1);
    IF stuck = NIL THEN Dark END;
    Oberon.Install(stuck)
  END
  END Run;

BEGIN
END Blink.
