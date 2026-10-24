-- 009: sessions.min_lap_time — per-session minimum lap time (seconds).
--
-- Crossings closer together than this on Layer 1's counter are treated as phantom
-- triggers by lapdata and dropped. It used to be only the MINIMUM_LAP_TIME env var, but
-- the right value depends on the circuit (~3s for ~5s laps; a small test circuit can lap
-- in under 2s), and a value that is too high silently discards genuine fast laps. The env
-- var remains lapdata's fallback when no race is staged or the API predates this column.
--
-- Apply to any database created before this migration:
--
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/009-sessions-min-lap-time.sql
--
-- ⚠️ Apply together with the new API image: RaceSession names min_lap_time in every
-- SELECT, so the new API breaks without the column.
--
-- Safe to re-run.

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS min_lap_time DOUBLE PRECISION NOT NULL DEFAULT 3;
