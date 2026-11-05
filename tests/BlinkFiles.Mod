MODULE BlinkFiles;  (* step 7. New file. BlinkMod was not edited. *)
(*
  The device serves two .rsc images from a byte table in HyperRAM.
  This host does not run the Oberon compiler, so the bytes and the
  reader are the encodings in sim/build_files_imem.py. The formulas
  are Files.Mod, on a directory instead of the disk Old:

    ReadByte     LDB, then advance the rider
    ReadInt      x := ((x3 * 100H + x2) * 100H + x1) * 100H + x0
    ReadString   ReadByte until 0X

  100H is LSL 8. The directory has two entries, each a name word, a
  base, and a length. Old returns the base, or 0 when neither name
  matches. A NIL file branches to the hold before the rider moves.
  HyperRAM powers up empty, so the CPU stores every byte of the
  table before it reads one back.
*)
  VAR base, rider: INTEGER;

  PROCEDURE Old*(name: INTEGER): INTEGER;
  BEGIN
    RETURN base
  END Old;

END BlinkFiles.
