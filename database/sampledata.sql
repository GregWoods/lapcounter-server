-- Active: 1738530390749@@127.0.0.1@5432@lapcounter_server

INSERT INTO car_manufacturers (id, name) VALUES (1, 'Scalextric') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_manufacturers (id, name) VALUES (2, 'Policar') ON CONFLICT (id) DO NOTHING;

INSERT INTO car_categories (id, name) VALUES (1, 'Porsche') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_categories (id, name) VALUES (2, 'Modern GT') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_categories (id, name) VALUES (3, 'Rally & Rallycross') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_categories (id, name) VALUES (4, 'Modern F1') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_categories (id, name) VALUES (5, 'Other') ON CONFLICT (id) DO NOTHING;

--Just one category per car_model for now

INSERT INTO car_models (id, car_category_id, manufacturer_id, name, race_number, model_number) 
    VALUES (1, 1, 1, 'Porsche 997 Red Teco/Burgfonds', '2', 'C2899') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_models (id, car_category_id, manufacturer_id, name, race_number, model_number) 
    VALUES (2, 1, 1, 'Porsche 997 Blue Morellato', '17', 'C2990') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_models (id, car_category_id, manufacturer_id, name, race_number, model_number)
    VALUES (3, 1, 1, 'Porsche 997 Yellow Forum Gelb', '46', 'C2691') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_models (id, car_category_id, manufacturer_id, name, race_number, model_number) 
    VALUES (4, 1, 1, 'Porsche 997 Black Mad Butcher', '1', 'C3132') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_models (id, car_category_id, manufacturer_id, name, race_number, model_number)
    VALUES (5, 1, 1, 'Porsche 997 Green Street', '', 'C3074') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_models (id, car_category_id, manufacturer_id, name, race_number, model_number) 
    VALUES (6, 1, 1, 'Porsche 997 Orange Street', '', 'C2871') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_models (id, car_category_id, manufacturer_id, name, race_number, model_number)
    VALUES (7, 1, 1, 'Porsche 997 Silver Street', '', 'C3021') ON CONFLICT (id) DO NOTHING;


INSERT INTO car_tyres (id, brand, compound, size) VALUES (1, 'Scalextric', ' Factory Rubber', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_tyres (id, brand, compound, size) VALUES (2, 'WASP', 'WASP 04', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_tyres (id, brand, compound, size) VALUES (3, 'Slot.it', 'P6', '18x10 Dwg 1207') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_tyres (id, brand, compound, size) VALUES (4, 'PCS', 'F22 Grey Race Control Tyre', '18x10') ON CONFLICT (id) DO NOTHING;


INSERT INTO chip_hardwares (id, name) VALUES (1, 'Scalextric C8515 Rev H') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_hardwares (id, name) VALUES (2, 'Scalextric C8515 Rev G') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_hardwares (id, name) VALUES (3, 'Scalextric C8515 Rev F') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_hardwares (id, name) VALUES (4, 'Scalextric C7005') ON CONFLICT (id) DO NOTHING;


INSERT INTO chip_firmwares (id, name) VALUES (1, 'Scalextric Factory Firmware') ON CONFLICT (id) DO NOTHING;  
INSERT INTO chip_firmwares (id, name) VALUES (2, 'InCar Pro 3.3') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_firmwares (id, name) VALUES (3, 'InCar Pro 4.0') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_firmwares (id, name) VALUES (4, 'InCar Pro 4.01') ON CONFLICT (id) DO NOTHING;


INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (1, 'Porsche Red/Black', 1, 1, false, '', 20.0, 1, 1, 'GT_Porsche_White.jpg', '')
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (2, 'Porsche Red/silver', 1, 1, false, '', 20.0, 1, 1, 'GT_Porsche_RedSilver.jpg', '') 
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (3, 'Porsche Blue/silver', 2, 1, false, '', 20.0, 1, 1, 'GT_Porsche_BlueSilver.jpg', '') 
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (4, 'Porsche Blue/Black', 2, 1, false, 'Slot.it Starter Kit Sidewinder 36t 17.3x8.25mm Wheels', 20.0, 1, 1, 'GT_Porsche_BlueBlack.jpg', '') 
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (5, 'Porsche Yellow', 3, 1, false, '', 20.0, 1, 1, 'GT_Porsche_Yellow.jpg', '') 
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (6, 'Porsche Black', 4, 1, false, '', 20.0, 1, 1, 'GT_Porsche_Black.jpg', '') 
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (7, 'Porsche Green', 5, 1, false, '', 20.0, 1, 1, 'GT_Porsche_Green.jpg', '') 
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (8, 'Porsche Orange', 6, 1, false, '', 20.0, 1, 1, 'GT_Porsche_Orange.jpg', '') 
    ON CONFLICT (id) DO NOTHING;
INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (9, 'Porsche Silver', 7, 1, false, '', 20.0, 1, 1, 'GT_Porsche_Silver.jpg', '') 
    ON CONFLICT (id) DO NOTHING;


INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (1, 'Alice', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (2, 'Bob', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (3, 'Charlie', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (4, 'Dave', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (5, 'Eve', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (6, 'Frank', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (7, 'Greg', 'Woods', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (8, 'Hannah', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (9, 'Jake', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (10, 'Liam', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (11, 'Mia', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (12, 'Noah', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid)
    VALUES (13, 'Olivia', '', '', '', '') ON CONFLICT (id) DO NOTHING;


INSERT INTO meetings (id, name, date, venue, count_first_crossing)
    VALUES (1, 'Junior Championship', '2024-06-01', 'Village Hall', false) ON CONFLICT (id) DO NOTHING;
INSERT INTO meetings (id, name, date, venue, count_first_crossing)
    VALUES (2, 'Garage Raceway', '2024-08-01', 'My Garage', false) ON CONFLICT (id) DO NOTHING;
INSERT INTO meetings (id, name, date, venue, count_first_crossing)
    VALUES (3, 'Village Hall Grand Prix', '2030-01-01', 'Village Hall', false) ON CONFLICT (id) DO NOTHING;
INSERT INTO meetings (id, name, date, venue, count_first_crossing)
    VALUES (4, '2031 Village Hall Grand Prix', '2031-02-01', 'Village Hall', false) ON CONFLICT (id) DO NOTHING;


INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 1, 'Alice')   ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 2, 'Bob')     ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 3, 'Charlie') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 4, 'Dave')    ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 5, 'Eve')     ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 6, 'Frank')   ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 7, 'Greg')    ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 8, 'Hannah')  ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 9, 'Jake')    ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 10, 'Liam')   ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 11, 'Mia')    ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 12, 'Noah')   ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 13, 'Olivia') ON CONFLICT (meeting_id, driver_id) DO NOTHING;


INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 2, 1) ON CONFLICT (meeting_id, car_id) DO NOTHING;  -- red car → red lane
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 7, 2) ON CONFLICT (meeting_id, car_id) DO NOTHING;  -- green car → green lane
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 3, 3) ON CONFLICT (meeting_id, car_id) DO NOTHING;  -- blue car → blue lane
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 5, 4) ON CONFLICT (meeting_id, car_id) DO NOTHING;  -- yellow car → yellow lane
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 8, 5) ON CONFLICT (meeting_id, car_id) DO NOTHING;  -- orange car → orange lane
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 9, 6) ON CONFLICT (meeting_id, car_id) DO NOTHING;  -- silver car → white lane
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 1, NULL) ON CONFLICT (meeting_id, car_id) DO NOTHING;  -- spare cars, unassigned
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 4, NULL) ON CONFLICT (meeting_id, car_id) DO NOTHING;
INSERT INTO meeting_cars (meeting_id, car_id, lane) VALUES (3, 6, NULL) ON CONFLICT (meeting_id, car_id) DO NOTHING;


INSERT INTO sessions (id, meeting_id, session_type, end_condition, end_condition_info, races_per_driver, scoring_method, scoring_points, start_time, end_time, state)
    VALUES (1, 3, 'FastestLap', 'Time', 3, 2, 'FastestLap', NULL, NULL, NULL, 'Finished') ON CONFLICT (id) DO NOTHING;
INSERT INTO sessions (id, meeting_id, session_type, end_condition, end_condition_info, races_per_driver, scoring_method, scoring_points, start_time, end_time, state)
    VALUES (2, 3, 'Points', 'Laps', 20, 3, 'PositionPoints', '[10, 8, 6, 4, 3, 2]', NULL, NULL, 'InProgress') ON CONFLICT (id) DO NOTHING;


INSERT INTO lanes (lane_number, color, enabled) VALUES (1, 'red', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (2, 'green', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (3, 'blue', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (4, 'yellow', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (5, 'orange', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (6, 'white', true) ON CONFLICT (lane_number) DO NOTHING;


INSERT INTO races (id, session_id, race_number, state) VALUES (1, 2, 1, 'Finished') ON CONFLICT (id) DO NOTHING;
INSERT INTO races (id, session_id, race_number, state) VALUES (2, 2, 2, 'Finished') ON CONFLICT (id) DO NOTHING;


-- Race 1: Alice L1, Bob L2, Charlie L3, Dave L4, Eve L5, Frank L6  (Greg/Hannah/Jake sit out)
-- Positions: P1 Bob(20L/9.567), P2 Eve(20L/9.876), P3 Alice(19L), P4 Dave(18L), P5 Frank(17L), P6 Charlie(16L)
INSERT INTO driver_races (id, driver_id, race_id, car_id, lane, laps_completed, fastest_lap_time) VALUES
    (1,  1, 1, 2, 1, 19, 10.234),  -- Alice   L1 P3
    (2,  2, 1, 7, 2, 20,  9.567),  -- Bob     L2 P1
    (3,  3, 1, 3, 3, 16, 12.123),  -- Charlie L3 P6
    (4,  4, 1, 5, 4, 18, 10.789),  -- Dave    L4 P4
    (5,  5, 1, 8, 5, 20,  9.876),  -- Eve     L5 P2
    (6,  6, 1, 9, 6, 17, 11.234)   -- Frank   L6 P5
    ON CONFLICT (id) DO NOTHING;

-- Race 2: Greg L1, Hannah L2, Jake L3, Alice L4, Bob L5, Charlie L6  (Dave/Eve/Frank sit out)
-- Positions: P1 Alice(20L/9.456), P2 Jake(20L/9.789), P3 Greg(19L), P4 Bob(18L), P5 Hannah(17L), P6 Charlie(16L)
INSERT INTO driver_races (id, driver_id, race_id, car_id, lane, laps_completed, fastest_lap_time) VALUES
    (7,  7, 2, 2, 1, 19, 10.123),  -- Greg    L1 P3
    (8,  8, 2, 7, 2, 17, 11.345),  -- Hannah  L2 P5
    (9,  9, 2, 3, 3, 20,  9.789),  -- Jake    L3 P2
    (10, 1, 2, 5, 4, 20,  9.456),  -- Alice   L4 P1
    (11, 2, 2, 8, 5, 18, 10.567),  -- Bob     L5 P4
    (12, 3, 2, 9, 6, 16, 12.456)   -- Charlie L6 P6
    ON CONFLICT (id) DO NOTHING;

-- Race 1 laps (sample — not all 20 per driver)
INSERT INTO driver_laps (id, driver_race_id, lap_time, created_at) VALUES
    -- Alice (dr 1, fastest 10.234)
    (1,  1, 13.456, '2030-01-01 15:00:00'), (2,  1, 11.789, '2030-01-01 15:00:13'),
    (3,  1, 10.234, '2030-01-01 15:00:25'), (4,  1, 12.567, '2030-01-01 15:00:36'),
    (5,  1, 11.890, '2030-01-01 15:00:48'),
    -- Bob (dr 2, fastest 9.567)
    (6,  2, 12.456, '2030-01-01 15:00:00'), (7,  2, 10.789, '2030-01-01 15:00:12'),
    (8,  2,  9.567, '2030-01-01 15:00:23'), (9,  2, 11.234, '2030-01-01 15:00:33'),
    (10, 2, 10.890, '2030-01-01 15:00:44'), (11, 2, 13.123, '2030-01-01 15:00:55'),
    -- Charlie (dr 3, fastest 12.123)
    (12, 3, 15.456, '2030-01-01 15:00:00'), (13, 3, 13.789, '2030-01-01 15:00:15'),
    (14, 3, 12.123, '2030-01-01 15:00:29'), (15, 3, 14.567, '2030-01-01 15:00:41'),
    (16, 3, 13.234, '2030-01-01 15:00:56'),
    -- Dave (dr 4, fastest 10.789)
    (17, 4, 13.456, '2030-01-01 15:00:00'), (18, 4, 12.234, '2030-01-01 15:00:13'),
    (19, 4, 10.789, '2030-01-01 15:00:25'), (20, 4, 13.567, '2030-01-01 15:00:36'),
    (21, 4, 12.789, '2030-01-01 15:00:50'),
    -- Eve (dr 5, fastest 9.876)
    (22, 5, 11.234, '2030-01-01 15:00:00'), (23, 5, 10.567, '2030-01-01 15:00:11'),
    (24, 5,  9.876, '2030-01-01 15:00:22'), (25, 5, 12.345, '2030-01-01 15:00:32'),
    (26, 5, 11.123, '2030-01-01 15:00:44'), (27, 5, 10.789, '2030-01-01 15:00:55'),
    -- Frank (dr 6, fastest 11.234)
    (28, 6, 14.567, '2030-01-01 15:00:00'), (29, 6, 12.890, '2030-01-01 15:00:15'),
    (30, 6, 11.234, '2030-01-01 15:00:28'), (31, 6, 13.678, '2030-01-01 15:00:39'),
    (32, 6, 12.456, '2030-01-01 15:00:53')
    ON CONFLICT (id) DO NOTHING;

-- Race 2 laps (sample — not all 20 per driver)
INSERT INTO driver_laps (id, driver_race_id, lap_time, created_at) VALUES
    -- Greg (dr 7, fastest 10.123)
    (33, 7, 13.234, '2030-01-01 16:00:00'), (34, 7, 11.456, '2030-01-01 16:00:13'),
    (35, 7, 10.123, '2030-01-01 16:00:24'), (36, 7, 12.567, '2030-01-01 16:00:34'),
    (37, 7, 11.890, '2030-01-01 16:00:47'),
    -- Hannah (dr 8, fastest 11.345)
    (38, 8, 14.456, '2030-01-01 16:00:00'), (39, 8, 13.123, '2030-01-01 16:00:14'),
    (40, 8, 11.345, '2030-01-01 16:00:27'), (41, 8, 14.567, '2030-01-01 16:00:38'),
    (42, 8, 13.890, '2030-01-01 16:00:53'),
    -- Jake (dr 9, fastest 9.789)
    (43, 9, 11.890, '2030-01-01 16:00:00'), (44, 9, 10.567, '2030-01-01 16:00:12'),
    (45, 9,  9.789, '2030-01-01 16:00:22'), (46, 9, 12.345, '2030-01-01 16:00:32'),
    (47, 9, 10.234, '2030-01-01 16:00:44'), (48, 9, 11.567, '2030-01-01 16:00:55'),
    -- Alice R2 (dr 10, fastest 9.456)
    (49, 10, 12.567, '2030-01-01 16:00:00'), (50, 10, 10.345, '2030-01-01 16:00:13'),
    (51, 10,  9.456, '2030-01-01 16:00:23'), (52, 10, 11.234, '2030-01-01 16:00:33'),
    (53, 10, 10.789, '2030-01-01 16:00:44'), (54, 10, 12.123, '2030-01-01 16:00:55'),
    -- Bob R2 (dr 11, fastest 10.567)
    (55, 11, 13.789, '2030-01-01 16:00:00'), (56, 11, 12.123, '2030-01-01 16:00:14'),
    (57, 11, 10.567, '2030-01-01 16:00:26'), (58, 11, 13.456, '2030-01-01 16:00:37'),
    (59, 11, 11.890, '2030-01-01 16:00:51'),
    -- Charlie R2 (dr 12, fastest 12.456)
    (60, 12, 15.678, '2030-01-01 16:00:00'), (61, 12, 13.890, '2030-01-01 16:00:16'),
    (62, 12, 12.456, '2030-01-01 16:00:30'), (63, 12, 15.123, '2030-01-01 16:00:42'),
    (64, 12, 14.567, '2030-01-01 16:00:57')
    ON CONFLICT (id) DO NOTHING;

-- Reset sequences so that auto-generated IDs don't collide with explicitly inserted sample data
SELECT setval(pg_get_serial_sequence('car_manufacturers', 'id'), MAX(id)) FROM car_manufacturers;
SELECT setval(pg_get_serial_sequence('car_categories', 'id'), MAX(id)) FROM car_categories;
SELECT setval(pg_get_serial_sequence('car_models', 'id'), MAX(id)) FROM car_models;
SELECT setval(pg_get_serial_sequence('car_tyres', 'id'), MAX(id)) FROM car_tyres;
SELECT setval(pg_get_serial_sequence('chip_hardwares', 'id'), MAX(id)) FROM chip_hardwares;
SELECT setval(pg_get_serial_sequence('chip_firmwares', 'id'), MAX(id)) FROM chip_firmwares;
SELECT setval(pg_get_serial_sequence('cars', 'id'), MAX(id)) FROM cars;
SELECT setval(pg_get_serial_sequence('drivers', 'id'), MAX(id)) FROM drivers;
SELECT setval(pg_get_serial_sequence('meetings', 'id'), MAX(id)) FROM meetings;
SELECT setval(pg_get_serial_sequence('sessions', 'id'), MAX(id)) FROM sessions;
SELECT setval(pg_get_serial_sequence('races', 'id'), MAX(id)) FROM races;
SELECT setval(pg_get_serial_sequence('driver_races', 'id'), MAX(id)) FROM driver_races;
SELECT setval(pg_get_serial_sequence('driver_laps', 'id'), MAX(id)) FROM driver_laps;
