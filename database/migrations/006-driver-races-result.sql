-- Each driver's result in a race, as lapdata ranked it (#81). lapdata is the one authority
-- on finishing position: the API's race_state subscriber copies these from the Finished
-- race_state, and the Results page reads them rather than re-ranking.
--
-- Both are NULL for a driver who never crossed the line (DNS), and for a race whose
-- Finished race_state never reached the API.

ALTER TABLE driver_races
    ADD COLUMN position INT,
    -- Seconds from lights-out to the driver's last counted crossing.
    ADD COLUMN race_time NUMERIC(10, 3);
