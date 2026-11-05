MODULE BlinkFetch;  (* step 4. New file. BlinkRsc and BlinkBoot were not edited. *)
(*
  One FixP store, then a fetch of that same address. This host does not run
  the Oberon compiler, so the image is the encodings from
  sim/build_fetchbl_imem.py. The formula is Modules.Mod, the BL fixup:

    offset := (dest - adr - 4) DIV 4;
    SYSTEM.PUT(adr, (offset MOD 1000000H) + 0F7000000H)

  adr is the address the CPU later fetches. The ROM at that address is a
  hold. The word that executes is the word read back from HyperRAM. A
  mismatch, or a fetch that still sees the ROM, holds the LED dark.
*)
  VAR adr, dest, offset, inst: INTEGER;

  PROCEDURE Go*;
  BEGIN
    dest := 1C00H; adr := 1F00H;
    offset := (dest - adr - 4) DIV 4;
    inst := (offset MOD 1000000H) + 0F7000000H
  END Go;

END BlinkFetch.
