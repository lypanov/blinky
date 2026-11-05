MODULE Blink5;  (* step 7. New file. Imports AMemoryMappedToggle. *)
(*
  Load reads Blink5.rsc from the byte table, then the imported
  AMemoryMappedToggle.rsc. The version byte must be 1X. Blink5's
  import key must equal the key ReadInt returns from the imported
  file, and each of those keys must equal the immediate in this
  image. The entry integer w must be 48H. The code base is the
  host-placed module at 1000H, so

    body := code + w

  is 1048H, the delay loop already fixed in the instruction ROM.
  The file's code count is 0 and fixorgT is 0. A zero-length chain
  is not chased. The CPU fetches the pROM, so Load does not execute
  a copy of the code section out of HyperRAM. A wrong name, a wrong
  version, a key that does not match, a zero w, or a trailing byte
  other than "O" branches to the hold. The LED stays dark.
*)
  VAR key, w, body: INTEGER;

  PROCEDURE Go*;
  BEGIN
    body := body + w
  END Go;

END Blink5.
