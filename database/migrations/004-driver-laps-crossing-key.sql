-- One row per Layer 1 crossing (#77). driver_lap is now delivered at least once (QoS 1, a
-- persistent dbwriter session, acked only after the commit), so the same crossing can
-- arrive twice; dbwriter inserts with ON CONFLICT DO NOTHING against this key.
--
-- Keyed on the crossing, not on a lap number: clock ids are never reused (clock contract
-- rule 3), so (clock, counter_ms) only repeats on a true redelivery. A lap number would
-- collide with a genuinely new lap whenever lapdata's count and the DB's drift, and the
-- new lap would be silently dropped. driver_race_id is in the key because two cars can
-- cross in the same 10 ms ARC tick on one clock, and both GPIO lanes share a clock.
--
-- Covers void crossings too: they are redelivered just like laps. Rows with a NULL clock
-- or counter_ms (from before #27) are never treated as duplicates, since a unique
-- constraint counts NULLs as distinct.
--
-- Fails if the database already holds duplicate crossings. There is no real data yet, so
-- rebuild it (CLAUDE.md, "Rebuild the database").

ALTER TABLE driver_laps ADD CONSTRAINT driver_laps_one_row_per_crossing
    UNIQUE (driver_race_id, clock, counter_ms);
