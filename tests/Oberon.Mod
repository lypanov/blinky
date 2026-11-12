MODULE Oberon;
  IMPORT Modules, SYSTEM;
  VAR r: INTEGER;

  (*command interpretation*)
  PROCEDURE Call* (name: ARRAY OF CHAR; VAR res: INTEGER);
    VAR mod: Modules.Module; P: Modules.Command;
      i, j: INTEGER; ch: CHAR;
      Mname, Cname: ARRAY 32 OF CHAR;
  BEGIN i := 0; ch := name[0];
    WHILE (ch # ".") & (ch # 0X) DO Mname[i] := ch; INC(i); ch := name[i] END ;
    IF ch = "." THEN
      Mname[i] := 0X; INC(i);
      Modules.Load(Mname, mod); res := Modules.res;
      IF Modules.res = 0 THEN
        j := 0; ch := name[i]; INC(i);
        WHILE ch # 0X DO Cname[j] := ch; INC(j); ch := name[i]; INC(i) END ;
        Cname[j] := 0X;
        P := Modules.ThisCommand(mod, Cname); res := Modules.res;
        IF Modules.res = 0 THEN P END
      END
    ELSE res := 5
    END
  END Call;

BEGIN
  (* Stage 11. Bit 8 stays clear until Blink.Run stores 10BH. *)
  SYSTEM.PUT(-84, 0BH);
  Call("Blink.Run", r);
  (* 5 is ThisCommand's miss. The blocks keep that byte. *)
  IF r # 0 THEN SYSTEM.PUT(-84, r) END ;
  REPEAT UNTIL FALSE
END Oberon.
