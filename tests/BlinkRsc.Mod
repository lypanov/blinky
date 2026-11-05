MODULE BlinkRsc;  (* step 3. New file. BlinkBoot was not edited. *)
(*
  LDB / STB and the start of Modules.Load. This host does not run the
  Oberon compiler, so the image is the same encodings from
  sim/build_rsc_imem.py (Put2 of Ldr+1 and Str+1, Put1 of LSL and ADD).
  The header bytes live in HyperRAM. They are written with STB and read
  with LDB. Expected name bytes, the key, the version and the size are
  immediates, not a second copy of the header. A mismatch holds the LED dark.

  Four byte stores at consecutive addresses must come back as one word
  44332211H, and a byte store must leave the next word alone.

  Files.ReadInt is little-endian:
    x := ((x3 * 100H + x2) * 100H + x1) * 100H + x0
  ORG compiles *100H as LSL 8.

  Modules.Load then requires the version byte to be versionkey (1X).
  The name compared here is "Blink5".
*)
  CONST versionkey = 1X;

  VAR name: ARRAY 8 OF CHAR;
    key, size: INTEGER;
    version: CHAR;

  PROCEDURE ReadInt(VAR x: INTEGER);
    VAR x0, x1, x2, x3: CHAR;
  BEGIN
    (* four ReadByte, then the shift above. The image does this with LDB. *)
    x0 := 0X; x1 := 0X; x2 := 0X; x3 := 0X;
    x := ((ORD(x3) * 100H + ORD(x2)) * 100H + ORD(x1)) * 100H + ORD(x0)
  END ReadInt;

  PROCEDURE Go*;
  BEGIN
    name := "Blink5";
    key := 13579BDFH;
    version := versionkey;
    size := 100H
  END Go;

END BlinkRsc.
