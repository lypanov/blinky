MODULE LightToggle;

IMPORT MMT := AMemoryMappedToggle;

VAR counter: INTEGER;
    maxIterations: INTEGER;

BEGIN
    counter := 0;
    maxIterations := 262144;

    WHILE TRUE DO
        INC(counter);
        IF counter >= maxIterations THEN
            MMT.Toggle; (* Use the toggle function from the imported module *)
            counter := 0;
        END;
    END;
END LightToggle.
