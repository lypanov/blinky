MODULE BlinkChain;  (* step 5. New file. BlinkFetch, BlinkRsc and BlinkBoot were not edited. *)
(*
  The device walks the P chain and the D chain. This host does not run the
  Oberon compiler, so the image is the encodings from sim/build_pdchain_imem.py.
  The formulas are Modules.Mod. The host no longer rewrites fixorgP or fixorgD.

    adr := code + fixorgP*4;
    WHILE adr # code DO
      SYSTEM.GET(adr, inst);
      mno := inst DIV 100000H MOD 10H; pno := inst DIV 1000H MOD 100H;
      disp := inst MOD 1000H;
      SYSTEM.GET(imp + (mno-1)*4, impmod);
      SYSTEM.GET(impmod.ent + pno*4, dest); dest := dest + impmod.code;
      offset := (dest - adr - 4) DIV 4;
      SYSTEM.PUT(adr, (offset MOD 1000000H) + 0F7000000H);
      adr := adr - disp*4
    END

    adr := code + fixorgD*4;
    WHILE adr # code DO
      SYSTEM.GET(adr, inst);
      mno := inst DIV 100000H MOD 10H; disp := inst MOD 1000H;
      IF mno = 0 THEN
        SYSTEM.PUT(adr, (inst DIV 1000000H * 10H + MT) * 100000H + modnum*4)
      ELSE
        SYSTEM.GET(imp + (mno-1)*4, impmod); v := impmod.num;
        SYSTEM.PUT(adr, (inst DIV 1000000H * 10H + MT) * 100000H + v*4);
        SYSTEM.GET(adr + 4, inst);
        vno := inst MOD 100H;
        SYSTEM.GET(impmod.ent + vno*4, offset);
        IF ODD(inst DIV 100H) THEN offset := offset + impmod.code - impmod.data END;
        SYSTEM.PUT(adr + 4, inst DIV 10000H * 10000H + offset)
      END;
      adr := adr - disp*4
    END

  The ROM contains the unfixed placeholders. A fetch of a fixed PC executes
  the word the walk stored. The two pairs after LightToggle are the import
  arms: MMT.light, and the address of Toggle (the ODD arm). They are outside
  the delay loop. A wrong word, or a fetch that still sees the placeholder,
  holds the LED dark.
*)
  VAR adr, inst, mno, pno, vno, disp, dest, offset, v: INTEGER;

  PROCEDURE Go*;
  BEGIN
    adr := 0
  END Go;

END BlinkChain.
