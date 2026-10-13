# Creates the database schema and loads mandatory reference data (the car catalog
# and the 6 physical lanes). Run once on a fresh database.
#
# Demo data is a separate, optional step - see sampledata.py.

from pathlib import Path
from sqlmodel import SQLModel, create_engine
from model import *
from settings import Settings


def create_engine_from_settings():
    settings = Settings()
    connection_string = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"
    print(f"Connection string: {connection_string}")
    return create_engine(connection_string)


def find_repo_file(*relative_parts: str) -> Path:
    """Locate a file that lives outside api/app/, in either environment this script
    runs in: a full repo checkout, or the api Docker container where compose mounts
    the repo's database/ folder read-only beside app/."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2].joinpath(*relative_parts),  # repo root (local run)
        here.parents[1].joinpath(*relative_parts),  # Docker: database/ mounted beside app/
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    tried = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"Could not find {Path(*relative_parts)} - tried: {tried}")


def run_sql_file(engine, sql_path: Path):
    raw = engine.raw_connection()
    try:
        raw.cursor().execute(sql_path.read_text())
        raw.commit()
    finally:
        raw.close()


def create_schema():
    SQLModel.metadata.create_all(create_engine_from_settings())


def load_reference_data():
    engine = create_engine_from_settings()
    run_sql_file(engine, find_repo_file('database', 'reference.sql'))
    print("Ran database/reference.sql")


if __name__ == "__main__":
    create_schema()
    print("All tables created successfully")
    load_reference_data()
    print("Reference data loaded successfully")
