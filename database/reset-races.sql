-- Full reset to known sample data state.
-- Removes all human-generated test races and restores sample data exactly.
--
-- Usage:
--   docker exec -i database psql -U lap -d lapcounter_server < database/reset-races.sql

-- 1. Wipe all race data in dependency order
DELETE FROM driver_laps;
DELETE FROM driver_races;
DELETE FROM races;

-- 2. Remove any sessions not in the original sample data; restore their states
DELETE FROM sessions WHERE id NOT IN (1, 2);
UPDATE sessions SET state = 'Finished'  WHERE id = 1;
UPDATE sessions SET state = 'InProgress' WHERE id = 2;

-- 3. Re-insert sample races (session 2 only — session 1 is a completed FastestLap warmup)
INSERT INTO races (id, session_id, state) VALUES (1, 2, 'Finished') ON CONFLICT (id) DO UPDATE SET state = 'Finished';
INSERT INTO races (id, session_id, state) VALUES (2, 2, 'Finished') ON CONFLICT (id) DO UPDATE SET state = 'Finished';

-- 4. Re-insert driver_races for races 1 and 2
-- Race 1: Alice L1, Bob L2, Charlie L3, Dave L4, Eve L5, Frank L6  (Greg/Hannah/Jake sit out)
-- Race 2: Greg L1, Hannah L2, Jake L3, Alice L4, Bob L5, Charlie L6  (Dave/Eve/Frank sit out)
INSERT INTO driver_races (id, driver_id, race_id, car_id, lane, laps_completed, fastest_lap_time)
    VALUES
        (1,  1, 1, 2, 1, 19, 10.234),  -- Alice   R1 L1 P3
        (2,  2, 1, 7, 2, 20,  9.567),  -- Bob     R1 L2 P1
        (3,  3, 1, 3, 3, 16, 12.123),  -- Charlie R1 L3 P6
        (4,  4, 1, 5, 4, 18, 10.789),  -- Dave    R1 L4 P4
        (5,  5, 1, 8, 5, 20,  9.876),  -- Eve     R1 L5 P2
        (6,  6, 1, 9, 6, 17, 11.234),  -- Frank   R1 L6 P5
        (7,  7, 2, 2, 1, 19, 10.123),  -- Greg    R2 L1 P3
        (8,  8, 2, 7, 2, 17, 11.345),  -- Hannah  R2 L2 P5
        (9,  9, 2, 3, 3, 20,  9.789),  -- Jake    R2 L3 P2
        (10, 1, 2, 5, 4, 20,  9.456),  -- Alice   R2 L4 P1
        (11, 2, 2, 8, 5, 18, 10.567),  -- Bob     R2 L5 P4
        (12, 3, 2, 9, 6, 16, 12.456)   -- Charlie R2 L6 P6
    ON CONFLICT (id) DO UPDATE SET
        driver_id        = EXCLUDED.driver_id,
        race_id          = EXCLUDED.race_id,
        car_id           = EXCLUDED.car_id,
        lane             = EXCLUDED.lane,
        laps_completed   = EXCLUDED.laps_completed,
        fastest_lap_time = EXCLUDED.fastest_lap_time;

-- 5. Re-insert sample driver_laps for races 1 and 2
INSERT INTO driver_laps (id, driver_race_id, lap_time, created_at) VALUES
    -- Race 1
    (1,  1, 13.456, '2030-01-01 15:00:00'), (2,  1, 11.789, '2030-01-01 15:00:13'),
    (3,  1, 10.234, '2030-01-01 15:00:25'), (4,  1, 12.567, '2030-01-01 15:00:36'),
    (5,  1, 11.890, '2030-01-01 15:00:48'),
    (6,  2, 12.456, '2030-01-01 15:00:00'), (7,  2, 10.789, '2030-01-01 15:00:12'),
    (8,  2,  9.567, '2030-01-01 15:00:23'), (9,  2, 11.234, '2030-01-01 15:00:33'),
    (10, 2, 10.890, '2030-01-01 15:00:44'), (11, 2, 13.123, '2030-01-01 15:00:55'),
    (12, 3, 15.456, '2030-01-01 15:00:00'), (13, 3, 13.789, '2030-01-01 15:00:15'),
    (14, 3, 12.123, '2030-01-01 15:00:29'), (15, 3, 14.567, '2030-01-01 15:00:41'),
    (16, 3, 13.234, '2030-01-01 15:00:56'),
    (17, 4, 13.456, '2030-01-01 15:00:00'), (18, 4, 12.234, '2030-01-01 15:00:13'),
    (19, 4, 10.789, '2030-01-01 15:00:25'), (20, 4, 13.567, '2030-01-01 15:00:36'),
    (21, 4, 12.789, '2030-01-01 15:00:50'),
    (22, 5, 11.234, '2030-01-01 15:00:00'), (23, 5, 10.567, '2030-01-01 15:00:11'),
    (24, 5,  9.876, '2030-01-01 15:00:22'), (25, 5, 12.345, '2030-01-01 15:00:32'),
    (26, 5, 11.123, '2030-01-01 15:00:44'), (27, 5, 10.789, '2030-01-01 15:00:55'),
    (28, 6, 14.567, '2030-01-01 15:00:00'), (29, 6, 12.890, '2030-01-01 15:00:15'),
    (30, 6, 11.234, '2030-01-01 15:00:28'), (31, 6, 13.678, '2030-01-01 15:00:39'),
    (32, 6, 12.456, '2030-01-01 15:00:53'),
    -- Race 2
    (33, 7, 13.234, '2030-01-01 16:00:00'), (34, 7, 11.456, '2030-01-01 16:00:13'),
    (35, 7, 10.123, '2030-01-01 16:00:24'), (36, 7, 12.567, '2030-01-01 16:00:34'),
    (37, 7, 11.890, '2030-01-01 16:00:47'),
    (38, 8, 14.456, '2030-01-01 16:00:00'), (39, 8, 13.123, '2030-01-01 16:00:14'),
    (40, 8, 11.345, '2030-01-01 16:00:27'), (41, 8, 14.567, '2030-01-01 16:00:38'),
    (42, 8, 13.890, '2030-01-01 16:00:53'),
    (43, 9, 11.890, '2030-01-01 16:00:00'), (44, 9, 10.567, '2030-01-01 16:00:12'),
    (45, 9,  9.789, '2030-01-01 16:00:22'), (46, 9, 12.345, '2030-01-01 16:00:32'),
    (47, 9, 10.234, '2030-01-01 16:00:44'), (48, 9, 11.567, '2030-01-01 16:00:55'),
    (49, 10, 12.567, '2030-01-01 16:00:00'), (50, 10, 10.345, '2030-01-01 16:00:13'),
    (51, 10,  9.456, '2030-01-01 16:00:23'), (52, 10, 11.234, '2030-01-01 16:00:33'),
    (53, 10, 10.789, '2030-01-01 16:00:44'), (54, 10, 12.123, '2030-01-01 16:00:55'),
    (55, 11, 13.789, '2030-01-01 16:00:00'), (56, 11, 12.123, '2030-01-01 16:00:14'),
    (57, 11, 10.567, '2030-01-01 16:00:26'), (58, 11, 13.456, '2030-01-01 16:00:37'),
    (59, 11, 11.890, '2030-01-01 16:00:51'),
    (60, 12, 15.678, '2030-01-01 16:00:00'), (61, 12, 13.890, '2030-01-01 16:00:16'),
    (62, 12, 12.456, '2030-01-01 16:00:30'), (63, 12, 15.123, '2030-01-01 16:00:42'),
    (64, 12, 14.567, '2030-01-01 16:00:57')
    ON CONFLICT (id) DO NOTHING;

-- 6. Reset sequences so new IDs don't collide with sample data
SELECT setval(pg_get_serial_sequence('sessions',     'id'), 2);
SELECT setval(pg_get_serial_sequence('races',        'id'), 4);
SELECT setval(pg_get_serial_sequence('driver_races', 'id'), 12);
SELECT setval(pg_get_serial_sequence('driver_laps',  'id'), 64);
