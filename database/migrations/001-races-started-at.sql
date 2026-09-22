-- 001: races.started_at — the lights-out ("go go go") instant.
--
-- Apply to any database created before this column existed. schema.sql is the
-- full-rebuild path and DROPs everything, so it is NOT the way to upgrade a
-- database that holds real meeting data (e.g. the race Pi's) — run this instead:
--
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/001-races-started-at.sql
--
-- Without it, the Race model names races.started_at in every SELECT, so *all* the
-- races endpoints (/races/pending/, /races/current/, /races/queue/, start, finish)
-- fail with UndefinedColumn — not just the new field. lapdata's POST is
-- fire-and-forget and only logs a warning, so the first visible symptom is the
-- NextRace and RaceControl pages 500ing.
--
-- Safe to re-run.

ALTER TABLE races ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NULL;
