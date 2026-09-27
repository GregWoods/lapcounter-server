-- 005: sessions.yellow_grace_power_pct / yellow_post_grace_power_pct /
-- yellow_lap_penalty_laps, plus a new race_penalties table.
--
-- Splits the old single "cars stay at full power for N seconds" yellow-flag behaviour
-- into a grace period (yellow_grace_seconds, added in 002) plus two power percentages:
-- how much power the cars get during the grace period, and how much they get once it
-- expires. BLE converts these to a Command characteristic multiplier; GPIO has no power
-- control at all, so the Admin form locks both to 100 when the running Layer 1 doesn't
-- advertise the power_control capability. See CLAUDE.md "Yellow flags: power-based
-- handling" and "Layer 1 capability advertising".
--
-- On GPIO, since power can't actually be cut, yellow_lap_penalty_laps is a substitute
-- deterrent: a driver who crosses the line after the grace period expires loses that
-- many laps, once per yellow-flag incident. Finishing Position (Points) sessions only —
-- FastestLap sessions rank by personal-best lap, so a lap made during/after a yellow
-- flag is already effectively self-penalizing.
--
-- race_penalties records every penalty applied (currently only 'lap') so a disputed
-- result can be re-checked after the meet, and so build_session_results() can fold the
-- penalty into final standings — the live in-memory reduction in lapdata's race_state
-- would otherwise be lost the moment the race ends and dbwriter's own
-- driver_races.laps_completed count takes over.
--
-- Apply to any database created before this migration:
--
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/005-sessions-yellow-power-and-penalty.sql
--
-- Skips migration numbers 003 (reserved in docs/lap-timing-plan.md for a future
-- session-level start-grid setting) and 004 (reserved in docs/per-car-power-plan.md for
-- a future safety_car_power column) — neither is built yet.
--
-- Safe to re-run.

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS yellow_grace_power_pct INT NOT NULL DEFAULT 100;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS yellow_post_grace_power_pct INT NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS yellow_lap_penalty_laps INT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS race_penalties (
    id SERIAL PRIMARY KEY,
    race_id INT NOT NULL REFERENCES races(id),
    driver_id INT NOT NULL REFERENCES drivers(id),
    penalty_type TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
