-- A new void crossing outcome (#120):
--   too_short  lap 1 no longer than the session's min_lap_time from lights-out — a car
--              sitting on the line, or rolling over it, as the lights went out. Void, and
--              lap 1 still runs from lights-out to the driver's next crossing.

ALTER TABLE driver_laps DROP CONSTRAINT driver_laps_outcome_valid;
ALTER TABLE driver_laps ADD CONSTRAINT driver_laps_outcome_valid
    CHECK (outcome IN ('counted', 'start_line', 'yellow_flag', 'baseline', 'too_short'));
