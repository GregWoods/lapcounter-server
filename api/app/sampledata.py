# Running this script will drop all tables and create them again, then add sample data.
# Before running this script, make sure you set the environment variables, or Pydantic validation will fail
# There is a setenv.ps1 file to do this, or running inside the "dev" Docker compose based container will set them for you.
#
# The actual sample data (drivers, cars, meetings, sessions, finished races and their
# laps) lives in one place: database/sampledata.sql. This script creates the schema,
# executes that file verbatim, then adds the one thing raw SQL can't express: session
# 2's upcoming race queue, which is a balanced schedule computed in Python
# (build_session_schedule(), the same function POST /sessions/{id}/regenerate-races
# uses). Keeping the row data in a single SQL file means this Python path and the
# `psql < database/sampledata.sql` path can never drift apart, the way a hand-maintained
# second copy of driver names once did.

from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine
from model import RaceSession, Lane
from settings import Settings


def _create_engine():
    try:
        settings = Settings()
        connection_string = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"
        print(f"Connection string: {connection_string}")
        return create_engine(connection_string)
    except Exception as e:
        print(f"Error creating engine: {e}")
        raise


def _find_repo_file(*relative_parts: str) -> Path:
    """Locate a file that lives outside api/app/, in either environment this script
    runs in: a full repo checkout (this file is api/app/sampledata.py, so the repo
    root is two levels up), or the api Docker container, where compose.dev.yaml mounts
    the repo's database/ folder read-only alongside app/ (one level up from this file,
    since only api/app/ itself — not api/ — is mounted into the container)."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2].joinpath(*relative_parts),  # repo root (local run)
        here.parents[1].joinpath(*relative_parts),  # Docker: database/ mounted beside app/
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    tried = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"Could not find {Path(*relative_parts)} — tried: {tried}")


def drop_tables():
    SQLModel.metadata.drop_all(_create_engine())


def create_db_and_tables():
    SQLModel.metadata.create_all(_create_engine())


def run_sql_file(engine, sql_path: Path):
    """Execute a .sql file's full text as one script, including sampledata.sql's
    multi-statement DO $$ ... $$ block. That block's embedded semicolons rule out
    naively splitting the file on ';' and running each piece through SQLModel's
    text(), so this goes straight to the DBAPI (psycopg2) connection instead, the
    same way `psql < file.sql` runs it."""
    raw = engine.raw_connection()
    try:
        raw.cursor().execute(sql_path.read_text())
        raw.commit()
    finally:
        raw.close()


def add_race_queue(session: Session):
    """Generate the upcoming race queue for the in-progress session, exactly as
    POST /sessions/{id}/regenerate-races does.

    Without this a fresh database has an InProgress session with no NotStarted races,
    so /races/pending/ 404s and NextRace shows an empty page until someone regenerates
    by hand. The schedule is balanced per driver and lane, so it cannot be written as
    fixed INSERTs - hence Python, not sampledata.sql. (sampledata.sql's own trailing
    setval() calls already sync every sequence this reads from — races, driver_races,
    driver_laps, drivers, meetings, sessions — so there's nothing to fix up here.)
    """
    from sqlmodel import select
    from next_race import (
        build_session_schedule, get_drivers_for_next_race_sql, save_session_schedule,
    )
    race_session = session.get(RaceSession, 2)
    lanes = session.exec(select(Lane).order_by(Lane.lane_number)).all()
    drivers = get_drivers_for_next_race_sql(session, race_session_id=race_session.id)
    schedule = build_session_schedule(race_session, drivers, lanes)
    count = save_session_schedule(session, schedule, race_session)
    session.commit()
    print(f"Generated {count} upcoming races for session {race_session.id}")


def add_sample_data():
    engine = _create_engine()
    run_sql_file(engine, _find_repo_file('database', 'sampledata.sql'))
    print("Ran database/sampledata.sql")
    with Session(engine) as session:
        add_race_queue(session)
    print("Sample data has been added successfully!")


if __name__ == "__main__":
    drop_tables()
    print("All tables dropped successfully")
    create_db_and_tables()
    print("All tables created successfully")
    add_sample_data()
    print("Sample data added successfully")
