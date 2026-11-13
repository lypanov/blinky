MODULE Oberon;
  IMPORT Input, Kernel, Modules, SYSTEM;

  CONST off = 0; idle = 1; active = 2;

  TYPE Task* = POINTER TO TaskDesc;
    Handler* = PROCEDURE;
    TaskDesc* = RECORD
      state, nextTime, period*: INTEGER;
      next: Task;
      handle: Handler
    END;

  VAR NofTasks*: INTEGER;
    Turns*: INTEGER;
    CurTask: Task;
    r: INTEGER;

  PROCEDURE Call* (name: ARRAY OF CHAR; VAR res: INTEGER);
    VAR mod: Modules.Module; P: Modules.Command;
      i, j: INTEGER; ch: CHAR;
      Mname, Cname: ARRAY 32 OF CHAR;
  BEGIN i := 0; ch := name[0];
    WHILE (ch # ".") & (ch # 0X) DO Mname[i] := ch; INC(i); ch := name[i] END;
    IF ch = "." THEN
      Mname[i] := 0X; INC(i);
      Modules.Load(Mname, mod); res := Modules.res;
      IF Modules.res = 0 THEN
        j := 0; ch := name[i]; INC(i);
        WHILE ch # 0X DO Cname[j] := ch; INC(j); ch := name[i]; INC(i) END;
        Cname[j] := 0X;
        P := Modules.ThisCommand(mod, Cname); res := Modules.res;
        IF Modules.res = 0 THEN P END
      END
    ELSE res := 5
    END
  END Call;

  PROCEDURE Idle;
  BEGIN
  END Idle;

  PROCEDURE NewTask*(h: Handler; period: INTEGER): Task;
    VAR t: Task;
  BEGIN NEW(t);
    IF t # NIL THEN
      t.state := off; t.next := t; t.handle := h; t.period := period
    END;
    RETURN t
  END NewTask;

  PROCEDURE Install* (T: Task);
  BEGIN
    IF (T # NIL) & (T.state = off) THEN
      T.next := CurTask.next; CurTask.next := T; T.state := idle; T.nextTime := 0; INC(NofTasks)
    END
  END Install;

  PROCEDURE Remove* (T: Task);
    VAR t: Task;
  BEGIN
    IF (T # NIL) & (T.state # off) THEN t := T;
      WHILE t.next # T DO t := t.next END;
      t.next := T.next; T.state := off; T.next := NIL; CurTask := t; DEC(NofTasks)
    END
  END Remove;

  (* The book's loop, without viewers. No key and no mouse button, so
     each turn takes the task branch. Turns counts those turns. A
     handler that does not return stops the loop, and the LED with it. *)
  PROCEDURE Loop*;
    VAR X, Y, t: INTEGER; keys: SET; ch: CHAR;
  BEGIN
    REPEAT
      INC(Turns);
      Input.Mouse(keys, X, Y);
      IF Input.Available() > 0 THEN
        Input.Read(ch)
      ELSIF keys # {} THEN
      ELSE
        CurTask := CurTask.next; t := Kernel.Time();
        IF t >= CurTask.nextTime THEN
          (* The book stores t + period. A late poll then stays late, and
             the gaps walk away from the period. Stepping from the previous
             deadline keeps the rate, and a poll that has already missed
             more than one period takes the book's t + period so it does
             not queue a burst. *)
          CurTask.nextTime := CurTask.nextTime + CurTask.period;
          IF CurTask.nextTime <= t THEN CurTask.nextTime := t + CurTask.period END;
          CurTask.state := active; CurTask.handle; CurTask.state := idle
        END
      END
    UNTIL FALSE
  END Loop;

BEGIN
  (* Stage 11. Bit 8 stays clear until Blink.Run stores 10BH. *)
  SYSTEM.PUT(-84, 0BH);
  NofTasks := 0; Turns := 0;
  CurTask := NewTask(Idle, 32767); Install(CurTask);
  Call("Blink.Run", r);
  IF r # 0 THEN SYSTEM.PUT(-84, r); REPEAT UNTIL FALSE END;
  Loop
END Oberon.
