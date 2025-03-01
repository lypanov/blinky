MODULE LightToggle;

VAR light: INTEGER;
    counter: INTEGER;
    maxIterations: INTEGER;

BEGIN
    light := 0;
    counter := 0;
    maxIterations := 16777216;

    WHILE TRUE DO
        INC(counter);
        IF counter >= maxIterations THEN
            light := 1 - light; (* toggle light, memory writes are intercepted *)
            counter := 0;
        END;
    END;
END LightToggle.
