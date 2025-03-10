
DROP TABLE IF EXISTS driver_laps;
DROP TABLE IF EXISTS driver_races;
DROP TABLE IF EXISTS races;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS meeting_cars;
DROP TABLE IF EXISTS meeting_drivers;
DROP TABLE IF EXISTS meetings;
DROP TABLE IF EXISTS drivers;
DROP TABLE IF EXISTS cars;
DROP TABLE IF EXISTS car_models;
DROP TABLE IF EXISTS car_categories;
DROP TABLE IF EXISTS chip_firmwares;
DROP TABLE IF EXISTS chip_hardwares;
DROP TABLE IF EXISTS car_tyres;
DROP TABLE IF EXISTS car_manufacturers;


CREATE TABLE car_manufacturers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE car_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

--The cars as they came out of the box.
CREATE TABLE car_models (
    id SERIAL PRIMARY KEY,
    car_category_id INT REFERENCES car_categories(id),
    manufacturer_id INT REFERENCES car_manufacturers(id),
    name VARCHAR(255) NOT NULL,
    race_number VARCHAR(255),
    model_number VARCHAR(255)
);

CREATE TABLE car_tyres (
    id SERIAL PRIMARY KEY,
    compound VARCHAR(255) NOT NULL,
    size VARCHAR(255) NOT NULL
);


CREATE TABLE chip_hardwares (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE chip_firmwares (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

--My cars, as they are configured for racing.
CREATE TABLE cars (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL, -- defaults to car_model.name, but can be overridden in the UI
    car_model_id INT REFERENCES car_models(id), 
    tyre_id INT REFERENCES car_tyres(id),
    magnet BOOLEAN, 
    weight_added DECIMAL, 
    modifications_notes TEXT,
    chip_hardware_id INT REFERENCES chip_hardwares(id), 
    chip_firmware_id INT REFERENCES chip_firmwares(id), 
    picture VARCHAR(255), -- Filename of car pic. No path or url
    rfid VARCHAR(255)
);


CREATE TABLE drivers (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    mobile_number VARCHAR(20),
    picture VARCHAR(255),   -- Filename of driver pic. No path or url
    rfid VARCHAR(255)
);


CREATE TABLE meetings (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    date DATE,
    venue VARCHAR(255)
);

CREATE TABLE meeting_drivers (
    meeting_id INT REFERENCES meetings(id),
    driver_id INT REFERENCES drivers(id),
    driver_name VARCHAR(255),   -- Generated. Usually just first_name, but may include last_name initial if 2 drivers have the same first name
    PRIMARY KEY (meeting_id, driver_id)
);

CREATE TABLE meeting_cars (
    meeting_id INT REFERENCES meetings(id),
    car_id INT REFERENCES cars(id),
    PRIMARY KEY (meeting_id, car_id)
);

CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    meeting_id INT REFERENCES meetings(id),
    session_type VARCHAR(255) CHECK (session_type IN ('Points', 'FastestLap', 'Championship')),
    end_condition VARCHAR(255) CHECK (end_condition IN ('Laps', 'Time')),
    end_condition_info INT,
    scoring VARCHAR(255) CHECK (scoring IN ('LapPoints', 'PositionPoints', 'FastestLap')),
    scoring_info TEXT,
    start_time TIME NULL,
    end_time TIME NULL
);

CREATE TABLE races (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES sessions(id),
    state VARCHAR(255) CHECK (state IN ('NotStarted', 'Running', 'Finished'))
);

-- links drivers with their cars for a particular race,
--   and links all drivers who are racing together.
-- Does not store any lap related data, which can all be derived from driver_lap
CREATE TABLE driver_races (
    id SERIAL PRIMARY KEY,
    driver_id INT REFERENCES drivers(id),
    race_id INT REFERENCES races(id),
    car_id INT REFERENCES cars(id),
    --laps_completed INT,
    --last_lap_time TIME,
    --fastest_lap_time TIME,
    UNIQUE (driver_id, race_id)
);

CREATE TABLE driver_laps (
    id SERIAL PRIMARY KEY,
    driver_race_id INT REFERENCES driver_races(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     --not used for laptimes, just for sorting
    --lap_number INT,     -- canbe derived
    lap_time DECIMAL(10,3)
);
