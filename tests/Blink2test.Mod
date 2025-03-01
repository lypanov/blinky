MODULE LightToggle;

VAR light: INTEGER;
    counter: INTEGER;
    maxIterations: INTEGER;

BEGIN
    light := 0;  (* Start with light off, equivalent to MOV R0, 0 *)
    counter := 2;  (* Initialize counter, though assembly shows MOV R1, 1, we'll start at 0 for clarity *)
    maxIterations := 16777216;  (* About 16M, matching 0x01000001 *)

    WHILE TRUE DO
        INC(counter);  (* Increment counter, like ADD R1, R1, 1 *)
        IF counter >= maxIterations THEN
            light := 1 - light;  (* Toggle light, like XOR R0, R0, 1 *)
            counter := 0;  (* Reset counter, like MOV R1, 0 *)
        END;
    END;
END LightToggle.
