-- 006: meetings.ended_at — a meeting is now ended manually, not by its date passing.
--
-- "Active meeting" used to mean the earliest meeting with date >= today, so a meeting
-- vanished from RaceControl the day after its date (or if it was created with the wrong
-- date) and every meeting-scoped endpoint 404'd. It now means the earliest meeting that
-- has not been ended; the operator ends it from the Admin meetings page
-- (POST /meetings/{id}/end).
--
-- Existing meetings: every meeting but the most recent by date is marked ended, so the
-- old pile of past meetings doesn't start shadowing the current one (the oldest unended
-- meeting wins). The most recent one stays open, which is what the old rule would have
-- picked on its date. Re-running is safe: only rows with ended_at IS NULL are touched,
-- and the newest never is.
--
-- Apply:
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/006-meetings-ended-at.sql
--
-- ⚠️ The new API selects meetings.ended_at, so deploy the migration and the API together.

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;

UPDATE meetings
   SET ended_at = NOW()
 WHERE ended_at IS NULL
   AND id <> (SELECT id FROM meetings ORDER BY date DESC NULLS LAST, id DESC LIMIT 1);
