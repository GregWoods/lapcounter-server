# Loads optional demo data (sample cars, drivers, meetings, sessions, finished
# races and laps) on top of an already-initialized schema.
#
# The schema and the mandatory reference data come from migrate.py (the `migrate`
# compose service), which has already run by the time the api container is up.

from pathlib import Path
from sqlmodel import Session, select
from model import RaceSession, Lane
from next_race import (
    build_session_schedule, get_drivers_for_next_race_sql, save_session_schedule,
)
from migrate import create_engine_from_settings, migrations_folder


def run_sql_file(engine, sql_path: Path):
    raw = engine.raw_connection()
    try:
        raw.cursor().execute(sql_path.read_text())
        raw.commit()
    finally:
        raw.close()


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
    run_sql_file(engine, migrations_folder().parent / 'sampledata.sql')
    print("Ran database/sampledata.sql")
    with Session(engine) as session:
        add_race_queue(session)
    print("Sample data added successfully")


if __name__ == "__main__":
    load_sample_data()
