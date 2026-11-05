MODULE BlinkBoot;  (* step 2. New file. No existing module was edited. *)
(*
  The checks below are what ORG emits for the operators Modules.Load uses
  when it pulls mno, pno and disp out of a fixup word, plus the conditions
  those compares compile to. This host does not run the Oberon compiler, so
  the image is the same encodings from sim/build_fixup_imem.py (Put0, Put1,
  Put3). A mismatch holds the LED dark.

  Sign-extended MOV:  k := -1                         must be 0FFFFFFFFH
  WHILE i < 4 DO INC(i) END                           GE, i ends at 4
  a := -2000000000; b := 2000000000; a < b           LT only if V works
  s := {0, 1, 2, 3}; t := {1}; s := s - t            ANN, result 0DH
  inst DIV 100000H MOD 10H                            ASR 20, AND 15
  inst DIV 1000H MOD 100H                             ASR 12, AND 0FFH
  inst MOD 1000H                                      AND 0FFFH
  inst MOD 1000000H                                   LSL 8, ROR 8
*)
  VAR i, s, t, a, b: INTEGER;

  PROCEDURE Go*;
  BEGIN
    i := 0;
    WHILE i < 4 DO INC(i) END;
    a := -2000000000; b := 2000000000;
    s := {0, 1, 2, 3}; t := {1}; s := s - t
  END Go;

END BlinkBoot.
