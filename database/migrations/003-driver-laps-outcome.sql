-- Every crossing lapdata acts on during a race is recorded, not only counted laps (#86),
-- so a crossing under a yellow flag or a discarded start-line crossing can be traced after
-- the meet and a race can one day be replayed. A void crossing is recorded exactly like a
-- lap, with no lap_time. `outcome` says why the crossing did or didn't count — never what
-- it cost, since penalties are their own fact (race_penalties):
--   counted     a real lap; the only rows with a lap_time, and the only rows anything
--               counts or takes a fastest lap from
--   start_line  the discarded part-lap from a grid behind the line
--   yellow_flag a crossing after a yellow-flag grace period expired: void. It may or may
--               not have incurred a lap penalty
--   baseline    the first crossing with nothing to time it from (after a lapdata
--               restart): it only becomes the next lap's starting point
-- Existing rows were all counted laps, hence the default.

ALTER TABLE driver_laps ADD COLUMN outcome VARCHAR(20) NOT NULL DEFAULT 'counted';
ALTER TABLE driver_laps ALTER COLUMN lap_time DROP NOT NULL;

ALTER TABLE driver_laps ADD CONSTRAINT driver_laps_outcome_valid
    CHECK (outcome IN ('counted', 'start_line', 'yellow_flag', 'baseline'));
-- A void crossing has no lap time, and a counted lap always has one.
ALTER TABLE driver_laps ADD CONSTRAINT driver_laps_lap_time_only_when_counted
    CHECK ((outcome = 'counted') = (lap_time IS NOT NULL));

-- Lap-timing provenance (#27), on every crossing, void ones included: the only way to
-- re-check a disputed lap after the meet. All nullable: rows from before this have none.
--   clock       Layer 1's clock id: counter_ms values compare only within one clock
--   counter_ms  Layer 1's own counter at the crossing. Two crossings on one clock
--               subtract exactly — this, not created_at, is when the car crossed
--   crossed_at  the crossing as wall-clock time, converted from counter_ms through the
--               anchor. For people reading the table; never time a lap with it.
--               created_at is when dbwriter wrote the row, up to seconds later.
-- How a lap was timed (driver_lap's `timing`) isn't stored: it follows from these rows —
-- lap 1 is from lights-out, the same clock as the previous row is an exact counter
-- subtraction, a different clock went through the anchor.
ALTER TABLE driver_laps ADD COLUMN clock VARCHAR(64);
ALTER TABLE driver_laps ADD COLUMN counter_ms BIGINT;
ALTER TABLE driver_laps ADD COLUMN crossed_at TIMESTAMPTZ;
