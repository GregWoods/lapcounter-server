-- Full reset to known sample data state.
-- Removes all human-generated test races and restores sample data exactly.
--
-- Usage:
--   docker exec -i database psql -U lap -d lapcounter_server < database/reset-races.sql

-- 1. Wipe all race data in dependency order
DELETE FROM driver_laps;
DELETE FROM driver_races;
DELETE FROM races;

-- 2. Remove any sessions not in the original sample data
DELETE FROM sessions WHERE id NOT IN (1, 2);

-- 3. Re-insert sample races (session 2 only — session 1 is a completed FastestLap warmup)
INSERT INTO races (id, session_id, state) VALUES (1, 2, 'Finished') ON CONFLICT (id) DO UPDATE SET state = 'Finished';
INSERT INTO races (id, session_id, state) VALUES (2, 2, 'Finished') ON CONFLICT (id) DO UPDATE SET state = 'Finished';

-- 4. Re-insert driver_races for race 2 with known lap results
INSERT INTO driver_races (id, driver_id, race_id, car_id, lane, laps_completed, fastest_lap_time)
    VALUES  (1, 1, 2, 2, 1, 5,  9.789),
            (2, 2, 2, 7, 2, 6, 10.345),
            (3, 3, 2, 3, 3, 2, 10.123),
            (4, 4, 2, 5, 4, 5, 11.345),
            (5, 5, 2, 8, 5, 6, 10.789),
            (6, 6, 2, 9, 6, 2, 11.567)
    ON CONFLICT (id) DO UPDATE SET
        driver_id = EXCLUDED.driver_id,
        race_id   = EXCLUDED.race_id,
        car_id    = EXCLUDED.car_id,
        lane      = EXCLUDED.lane,
        laps_completed   = EXCLUDED.laps_completed,
        fastest_lap_time = EXCLUDED.fastest_lap_time;

-- 5. Re-insert sample driver_laps for race 2
INSERT INTO driver_laps (id, driver_race_id, lap_time, created_at) VALUES
    (1,  1, 12.345, '2024-06-01 14:30:00'),
    (2,  1, 11.567, '2024-06-01 14:30:10'),
    (3,  1,  9.789, '2024-06-01 14:30:20'),
    (4,  1, 14.345, '2024-06-01 14:30:30'),
    (5,  1, 16.678, '2024-06-01 14:30:40'),
    (6,  2, 13.456, '2024-06-01 14:30:00'),
    (7,  2, 12.678, '2024-06-01 14:30:10'),
    (8,  2, 11.789, '2024-06-01 14:30:20'),
    (9,  2, 10.345, '2024-06-01 14:30:30'),
    (10, 2, 14.678, '2024-06-01 14:30:40'),
    (11, 2, 15.789, '2024-06-01 14:30:50'),
    (12, 3, 10.123, '2024-06-01 14:30:00'),
    (13, 3, 11.456, '2024-06-01 14:30:10'),
    (14, 4, 13.567, '2024-06-01 14:30:00'),
    (15, 4, 12.789, '2024-06-01 14:30:10'),
    (16, 4, 11.345, '2024-06-01 14:30:20'),
    (17, 4, 14.678, '2024-06-01 14:30:30'),
    (18, 4, 15.789, '2024-06-01 14:30:40'),
    (19, 5, 12.123, '2024-06-01 14:30:00'),
    (20, 5, 11.456, '2024-06-01 14:30:10'),
    (21, 5, 10.789, '2024-06-01 14:30:20'),
    (22, 5, 13.345, '2024-06-01 14:30:30'),
    (23, 5, 14.678, '2024-06-01 14:30:40'),
    (24, 5, 15.789, '2024-06-01 14:30:50'),
    (25, 6, 12.345, '2024-06-01 14:30:00'),
    (26, 6, 11.567, '2024-06-01 14:30:10')
    ON CONFLICT (id) DO NOTHING;

-- 6. Reset sequences so new IDs don't collide with sample data
SELECT setval(pg_get_serial_sequence('sessions',     'id'), 2);
SELECT setval(pg_get_serial_sequence('races',        'id'), 4);
SELECT setval(pg_get_serial_sequence('driver_races', 'id'), 12);
SELECT setval(pg_get_serial_sequence('driver_laps',  'id'), 26);
