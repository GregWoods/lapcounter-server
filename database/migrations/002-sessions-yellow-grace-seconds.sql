-- 002: sessions.yellow_grace_seconds — power-based yellow flag grace period.
--
-- On a yellow flag, cars now keep racing at full power for this many seconds
-- (state 'Yellow'), then lapdata auto-transitions to 'Paused' and BLE cuts power
-- (POWER_ON_TIMER_HALT) instead of leaving cars running indefinitely at full speed.
-- See CLAUDE.md "Yellow flags: power-based handling".
--
-- Apply to any database created before this column existed:
--
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/002-sessions-yellow-grace-seconds.sql
--
-- Without it, RaceSession names yellow_grace_seconds in every SELECT, so all the
-- sessions/races endpoints fail with UndefinedColumn.
--
-- Safe to re-run.

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS yellow_grace_seconds INT NOT NULL DEFAULT 5;
