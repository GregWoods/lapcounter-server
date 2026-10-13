-- Mandatory reference data: the car catalog (manufacturers, categories, models,
-- tyres, chip hardware/firmware) and the 6 physical track lanes.
--
-- Loaded by python init_db.py (or psql -f database/reference.sql) on a fresh
-- database. Idempotent: every row uses ON CONFLICT DO NOTHING.
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

INSERT INTO lanes (lane_number, color, enabled) VALUES (1, 'red', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (2, 'green', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (3, 'blue', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (4, 'yellow', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (5, 'orange', true) ON CONFLICT (lane_number) DO NOTHING;
INSERT INTO lanes (lane_number, color, enabled) VALUES (6, 'white', true) ON CONFLICT (lane_number) DO NOTHING;

SELECT setval(pg_get_serial_sequence('car_manufacturers', 'id'), MAX(id)) FROM car_manufacturers;
SELECT setval(pg_get_serial_sequence('car_categories', 'id'), MAX(id)) FROM car_categories;
SELECT setval(pg_get_serial_sequence('car_models', 'id'), MAX(id)) FROM car_models;
SELECT setval(pg_get_serial_sequence('car_tyres', 'id'), MAX(id)) FROM car_tyres;
SELECT setval(pg_get_serial_sequence('chip_hardwares', 'id'), MAX(id)) FROM chip_hardwares;
SELECT setval(pg_get_serial_sequence('chip_firmwares', 'id'), MAX(id)) FROM chip_firmwares;
