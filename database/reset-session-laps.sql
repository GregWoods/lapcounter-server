-- Wipe all lap data for the current InProgress session without touching the session itself.
-- Races are reset to NotStarted so they can be re-run.
-- After running this, restart lapdata to clear its in-memory state:
--   docker compose -f compose.dev.yaml restart lapdata
--
-- Usage:
--   docker exec -i database psql -U lap -d lapcounter_server < database/reset-session-laps.sql

-- Delete lap times for every race in the InProgress session.
-- Races and driver_races are left intact.
DELETE FROM driver_laps
WHERE driver_race_id IN (
    SELECT dr.id FROM driver_races dr
    JOIN races r ON dr.race_id = r.id
    WHERE r.session_id = (SELECT id FROM sessions WHERE state = 'InProgress' LIMIT 1)
);
