CREATE TABLE drivers (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    mobile_number VARCHAR(20),
    picture BYTEA,
    rfid VARCHAR(255)
);

CREATE TABLE cars (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    picture BYTEA,
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
    PRIMARY KEY (meeting_id, driver_id),

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
    session_id INT REFERENCES sessions(id)
    state VARCHAR(255) CHECK (state IN ('NotStarted', 'Running', 'Finished')),
);

CREATE TABLE driver_race (
    driver_id INT REFERENCES drivers(id),
    race_id INT REFERENCES races(id),
    car_id INT REFERENCES cars(id),
    laps_completed INT,
    last_lap_time TIME,
    fastest_lap_time TIME,
    PRIMARY KEY (driver_id, race_id)
);

CREATE TABLE driver_lap (
    driver_race_id INT REFERENCES driver_race(driver_id),
    lap_number INT,
    lap_time TIME,
    PRIMARY KEY (driver_race_id, lap_number)
);
