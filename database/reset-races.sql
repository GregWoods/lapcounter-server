-- Reset transient race data so the next GET /races/pending/ creates a fresh lineup.
-- Static data (drivers, cars, meetings, sessions, lanes) is left untouched.
-- Finished races and their lap history are preserved.
--
-- Usage:
--   docker exec -i database psql -U lap -d lapcounter_server < database/reset-races.sql

DELETE FROM driver_laps
WHERE driver_race_id IN (
    SELECT dr.id FROM driver_races dr
    JOIN races r ON r.id = dr.race_id
    WHERE r.state != 'Finished'
);

DELETE FROM driver_races
WHERE race_id IN (SELECT id FROM races WHERE state != 'Finished');

DELETE FROM races WHERE state != 'Finished';
