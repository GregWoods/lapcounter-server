-- 003: sessions.start_grid — moves "first crossing counts as lap 1" from the meeting
-- to the session.
--
-- A meeting can have more than one physical track/grid set up during it, so this can no
-- longer be a meeting-wide setting — it has to vary per session. See CLAUDE.md
-- "Discarded first crossing" and docs/lap-timing-plan.md decision 2, which designed this
-- move (this migration number was reserved there alongside an allow_jump_starts setting
-- that is a separate, still-unimplemented feature and is NOT part of this migration).
--
-- Replaces the boolean meetings.count_first_crossing with an enum sessions.start_grid:
-- 'InFrontOfLine' (today's count_first_crossing = true — the first crossing is lap 1) or
-- 'BehindLine' (today's default, false — the first crossing is a discarded part-lap and
-- lap 1 finishes at the second crossing). Lap 1 is timed from lights-out either way.
--
-- Apply to any database created before this migration:
--
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/003-sessions-start-grid.sql
--
-- ⚠️ The old API image selects meetings.count_first_crossing, so it breaks the moment
-- this migration runs. Apply the migration and deploy the new API together.
--
-- Safe to re-run.

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS start_grid VARCHAR(20) NOT NULL DEFAULT 'BehindLine'
    CHECK (start_grid IN ('InFrontOfLine', 'BehindLine'));

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'meetings' AND column_name = 'count_first_crossing'
    ) THEN
        UPDATE sessions
        SET start_grid = CASE WHEN meetings.count_first_crossing THEN 'InFrontOfLine' ELSE 'BehindLine' END
        FROM meetings
        WHERE sessions.meeting_id = meetings.id;

        ALTER TABLE meetings DROP COLUMN count_first_crossing;
    END IF;
END $$;
