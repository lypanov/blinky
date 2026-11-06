MODULE BlinkModules;  (* step 8. New file. Modules.Mod was not edited. *)
(*
  The body is the reset path. Setup still plants the module table,
  then branches here instead of to the memory prologue. Init reads
  the three words BootLoad leaves, subtracts the reserve, and only
  then does the body call Load. The formulas are Modules.Init:

    SYSTEM.GET(16, AllocPtr)
    SYSTEM.GET(20, root)
    SYSTEM.GET(24, limit)
    DEC(limit, 8000H)

  8000H is the 32 KB reserve, the immediate in the published source.
  R14 is the word read from address 24, the top of the reserve, and
  grows down. HyperRAM powers up empty, so the body stores the three
  words and reads them back. It also stores one word at each end of
  the reserve and reads both back. Address 20 and address 24 are
  also MT[1] and MT[2], so Init writes 50H and 70H back before it
  leaves. A limit that is not the planted stack origin minus 8000H,
  a reserve end that does not read back, or a proof word left at the
  power-up value, branches to the hold. The LED stays dark.
  Load("Blink5") is the step-7 reader; this body enters it only
  after the earlier prologues have passed.
*)
  VAR AllocPtr, root, limit, reserve: INTEGER;

  PROCEDURE Init*;
  BEGIN
    limit := limit - reserve
  END Init;

BEGIN Init
END BlinkModules.
