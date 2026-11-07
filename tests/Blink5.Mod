MODULE Blink5;  (* step 7. New file. Imports AMemoryMappedToggle. *)
(*
  Load reads Blink5.rsc from the byte table, then the imported
  AMemoryMappedToggle.rsc. The version byte must be 1X. Blink5's
  import key must equal the key ReadInt returns from the imported
  file, and each of those keys must equal the immediate in this
  image. The entry integer w must be 48H. That names the delay loop
  the walker has already fixed in page 10H.

  The placer then copies those fixed words to 2200H, rewrites the
  one BL so it still reaches Toggle, and walks one type entry at
  2304H. mno is 0, so the stored word becomes the data address plus
  vno. The body fetched after that copy is 2200H, in external
  memory. Reset, training, and this loader stay in the pROM. A wrong
  name, a wrong version, a key that does not match, a zero w, a
  trailing byte other than "O", a copied GetSB that is still the
  placeholder, or a type word that does not come back fixed branches
  to the hold. The LED stays dark.
*)
  VAR key, w, body: INTEGER;

  PROCEDURE Go*;
  BEGIN
    body := body + w
  END Go;

END Blink5.
