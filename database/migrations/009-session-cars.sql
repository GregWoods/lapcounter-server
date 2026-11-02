-- Which car is on each digital ID (lane) for a session, as the operator set it (#111).
--
-- A meeting has a pool of cars, any of which can be given any ID, and a session can run
-- an entirely different set from the last one; a faulty car is swapped for another on the
-- same ID between races. So the lane -> car mapping belongs to a session, and must
-- outlive its queued races: regenerating the queue, enabling a lane, adding a driver, or
-- generating the queue of a session not yet started all build races from it.
--
-- A lane with no row here falls back to the meeting's last finished race, then
-- meeting_cars, as before. Finished races keep the car they were raced with
-- (driver_races.car_id); only queued races follow an edit.

CREATE TABLE session_cars (
    session_id INT REFERENCES sessions(id),
    lane INT NOT NULL CHECK (lane BETWEEN 1 AND 6),
    car_id INT NOT NULL REFERENCES cars(id),
    PRIMARY KEY (session_id, lane)
);
