MODULE BlinkMod;  (* step 6. New file. BlinkChain was not edited. *)
(*
  The device fills a ModDesc, installs the module table, and calls a
  procedure variable. This host does not run the Oberon compiler, so the
  image is the encodings from sim/build_moddesc_imem.py. The formulas are
  Modules.Mod. DescSize is 80. The fields used here are

    name at 0, next at 32, num at 40, data at 52, code at 56

  The table entry and the call are

    SYSTEM.PUT(num * 4 + MTOrg, data)
    body := code + w
    body

  MTOrg is R12. w is the entry integer Load reads before it calls the
  body. The call is BLR, so R15 becomes the return address. That
  procedure checks R15, then enters LightToggle. The setup's module
  table is cleared first, so GetSB of light and of the counter uses the
  installed words. A wrong descriptor, a wrong table entry, or a jump
  that does not plant the link holds the LED dark.
*)
  VAR num, data, code, w, body: INTEGER;

  PROCEDURE Go*;
  BEGIN
    body := code + w
  END Go;

END BlinkMod.
