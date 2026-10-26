-- Each driver's position in a Fastest Lap session, as lapdata ranked it (#112). lapdata is
-- the one authority on that ranking: the API's race_state subscriber copies it from each
-- Finished race_state, and the Results page reads it rather than re-ranking.
--
-- NULL for a driver with no counted lap in the session (unranked), for every driver in a
-- Points session (their positions are per race, in driver_races.position, #81), and until
-- a Finished race_state for the session reaches the API.

ALTER TABLE session_drivers
    ADD COLUMN position INT;
