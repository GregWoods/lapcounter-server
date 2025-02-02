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


INSERT INTO car_tyres (id, compound, size) VALUES (1, 'Scalextric Factory Rubber', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_tyres (id, compound, size) VALUES (2, 'WASP', 'WASP 04') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_tyres (id, compound, size) VALUES (3, 'Slot.it P6', '18x10 Dwg 1207') ON CONFLICT (id) DO NOTHING;
INSERT INTO car_tyres (id, compound, size) VALUES (4, 'PCS F22 Grey Race Control Tyre', '18x10') ON CONFLICT (id) DO NOTHING;


INSERT INTO chip_hardware (id, name) VALUES (1, 'Scalextric C8515 Rev H') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_hardware (id, name) VALUES (2, 'Scalextric C8515 Rev G') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_hardware (id, name) VALUES (3, 'Scalextric C8515 Rev F') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_hardware (id, name) VALUES (4, 'Scalextric C7005') ON CONFLICT (id) DO NOTHING;


INSERT INTO chip_firmware (id, name) VALUES (1, 'Scalextric Factory Firmware') ON CONFLICT (id) DO NOTHING;  
INSERT INTO chip_firmware (id, name) VALUES (2, 'InCar Pro 3.3') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_firmware (id, name) VALUES (3, 'InCar Pro 4.0') ON CONFLICT (id) DO NOTHING;
INSERT INTO chip_firmware (id, name) VALUES (4, 'InCar Pro 4.01') ON CONFLICT (id) DO NOTHING;


INSERT INTO cars (id, name, car_model_id, tyre_id, magnet, modifications_notes, weight_added, chip_hardware_id, chip_firmware_id, picture, rfid) 
    VALUES (1, 'Porsche Red/Black', 1, 1, false, '', 20.0, 1, 1, 'GT_Porsche_RedBlack.jpg', '') 
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
    VALUES (1, 'Driver A', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (2, 'Driver B', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (3, 'Driver C', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (4, 'Driver D', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (5, 'Driver E', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (6, 'Driver F', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (7, 'Driver G', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (8, 'Driver H', '', '', '', '') ON CONFLICT (id) DO NOTHING;
INSERT INTO drivers (id, first_name, last_name, mobile_number, picture, rfid) 
    VALUES (9, 'Driver J', '', '', '', '') ON CONFLICT (id) DO NOTHING;


INSERT INTO meetings (id, name, date, venue) 
    VALUES (1, 'Junior Championship', '2024-06-01', 'Village Hall') ON CONFLICT (id) DO NOTHING;
INSERT INTO meetings (id, name, date, venue) 
    VALUES (2, 'Garage Raceway', '2024-08-01', 'My Garage') ON CONFLICT (id) DO NOTHING;
INSERT INTO meetings (id, name, date, venue) 
    VALUES (3, 'Village Hall Grand Prix', '2025-02-01', 'Village Hall') ON CONFLICT (id) DO NOTHING;


INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 1, 'Driver A') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 2, 'Driver B') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 3, 'Driver C') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 4, 'Driver D') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 5, 'Driver E') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 6, 'Driver F') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 7, 'Driver G') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 8, 'Driver H') ON CONFLICT (meeting_id, driver_id) DO NOTHING;
INSERT INTO meeting_drivers (meeting_id, driver_id, driver_name) VALUES (3, 9, 'Driver J') ON CONFLICT (meeting_id, driver_id) DO NOTHING;


INSERT INTO meeting_cars (meeting_id, car_id) VALUES (3, 1) ON CONFLICT (meeting_id, car_id) DO NOTHING;
INSERT INTO meeting_cars (meeting_id, car_id) VALUES (3, 2) ON CONFLICT (meeting_id, car_id) DO NOTHING;
INSERT INTO meeting_cars (meeting_id, car_id) VALUES (3, 3) ON CONFLICT (meeting_id, car_id) DO NOTHING;
INSERT INTO meeting_cars (meeting_id, car_id) VALUES (3, 4) ON CONFLICT (meeting_id, car_id) DO NOTHING;
INSERT INTO meeting_cars (meeting_id, car_id) VALUES (3, 5) ON CONFLICT (meeting_id, car_id) DO NOTHING;
INSERT INTO meeting_cars (meeting_id, car_id) VALUES (3, 6) ON CONFLICT (meeting_id, car_id) DO NOTHING;


INSERT INTO sessions (id, meeting_id, session_type, end_condition, end_condition_info, scoring, scoring_info, start_time, end_time) 
    VALUES (1, 3, 'FastestLap', 'Laps', 3, 'FastestLap', NULL, '14:30', '15:00') ON CONFLICT (id) DO NOTHING;
INSERT INTO sessions (id, meeting_id, session_type, end_condition, end_condition_info, scoring, scoring_info, start_time, end_time) 
    VALUES (2, 3, 'Points', 'Laps', 20, 'PositionPoints', NULL, '15:00', NULL) ON CONFLICT (id) DO NOTHING;


INSERT INTO races (id, session_id, state) VALUES (1, 2, 'Finished') ON CONFLICT (id) DO NOTHING;
INSERT INTO races (id, session_id, state) VALUES (2, 2, 'Finished') ON CONFLICT (id) DO NOTHING;
INSERT INTO races (id, session_id, state) VALUES (3, 2, 'Running') ON CONFLICT (id) DO NOTHING;
INSERT INTO races (id, session_id, state) VALUES (4, 2, 'NotStarted') ON CONFLICT (id) DO NOTHING;


INSERT INTO driver_race (id, driver_id, race_id, car_id) VALUES (1, 1, 2, 1) ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_race (id, driver_id, race_id, car_id) VALUES (2, 2, 2, 1) ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_race (id, driver_id, race_id, car_id) VALUES (3, 3, 2, 2) ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_race (id, driver_id, race_id, car_id) VALUES (4, 4, 2, 3) ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_race (id, driver_id, race_id, car_id) VALUES (5, 5, 2, 4) ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_race (id, driver_id, race_id, car_id) VALUES (6, 6, 2, 5) ON CONFLICT (id) DO NOTHING;

-- sample driver_laps data for the race which has already finished

-- Driver 1, 5 laps completed
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (1, 1, 12.345, '2024-06-01 14:30:00') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (2, 1, 11.567, '2024-06-01 14:30:10') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (3, 1, 9.789, '2024-06-01 14:30:20') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (4, 1, 14.345, '2024-06-01 14:30:30') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (5, 1, 16.678, '2024-06-01 14:30:40') ON CONFLICT (id) DO NOTHING;

--Driver 2, 6 laps completed
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (6, 2, 13.456, '2024-06-01 14:30:00') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (7, 2, 12.678, '2024-06-01 14:30:10') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (8, 2, 11.789, '2024-06-01 14:30:20') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (9, 2, 10.345, '2024-06-01 14:30:30') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (10, 2, 14.678, '2024-06-01 14:30:40') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (11, 2, 15.789, '2024-06-01 14:30:50') ON CONFLICT (id) DO NOTHING;

--Driver 3, 2 laps completed
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (12, 3, 10.123, '2024-06-01 14:30:00') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (13, 3, 11.456, '2024-06-01 14:30:10') ON CONFLICT (id) DO NOTHING;

-- Driver 4, 5 laps completed
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (14, 4, 13.567, '2024-06-01 14:30:00') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (15, 4, 12.789, '2024-06-01 14:30:10') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (16, 4, 11.345, '2024-06-01 14:30:20') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (17, 4, 14.678, '2024-06-01 14:30:30') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (18, 4, 15.789, '2024-06-01 14:30:40') ON CONFLICT (id) DO NOTHING;

-- Driver 5, 6 laps completed
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (19, 5, 12.123, '2024-06-01 14:30:00') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (20, 5, 11.456, '2024-06-01 14:30:10') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (21, 5, 10.789, '2024-06-01 14:30:20') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (22, 5, 13.345, '2024-06-01 14:30:30') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (23, 5, 14.678, '2024-06-01 14:30:40') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (24, 5, 15.789, '2024-06-01 14:30:50') ON CONFLICT (id) DO NOTHING;

-- Driver 6, 2 laps completed
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (25, 6, 12.345, '2024-06-01 14:30:00') ON CONFLICT (id) DO NOTHING;
INSERT INTO driver_lap (id, driver_race_id, lap_time, created_at) VALUES (26, 6, 11.567, '2024-06-01 14:30:10') ON CONFLICT (id) DO NOTHING;


-- leave driver laps empty for the current race... they will be generated in code
-- INSERT INTO driver_lap (driver_race_id, lap_time, created_at) VALUES (1, 12.345, '2024-06-01 14:30:00') ON CONFLICT (id) DO NOTHING;
