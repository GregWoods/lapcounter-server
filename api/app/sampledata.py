# Loads optional demo data (sample cars, drivers, meetings, sessions, finished
# races and laps) on top of an already-initialized schema.
#
# Run init_db.py first to create the schema and load the mandatory reference data.

from sqlmodel import Session, select
from model import RaceSession, Lane
from next_race import (
    build_session_schedule, get_drivers_for_next_race_sql, save_session_schedule,
)
from init_db import create_engine_from_settings, find_repo_file, run_sql_file


def add_race_queue(session: Session):
    race_session = session.get(RaceSession, 2)
    lanes = session.exec(select(Lane).order_by(Lane.lane_number)).all()
    drivers = get_drivers_for_next_race_sql(session, race_session_id=race_session.id)
    schedule = build_session_schedule(race_session, drivers, lanes)
    count = save_session_schedule(session, schedule, race_session)
    session.commit()
    print(f"Generated {count} upcoming races for session {race_session.id}")


def load_sample_data():
    engine = create_engine_from_settings()
    run_sql_file(engine, find_repo_file('database', 'sampledata.sql'))
    print("Ran database/sampledata.sql")
    with Session(engine) as session:
        add_race_queue(session)
    print("Sample data added successfully")


if __name__ == "__main__":
    load_sample_data()
