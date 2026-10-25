# model.py describes the tables for the ORM; database/migrations/ builds them (#84).
# Nothing forces the two to agree, so this checks the ways a mismatch actually breaks
# things: SQLModel names every mapped column in its SELECTs (one missing column takes
# out all of that table's endpoints with UndefinedColumn), and an ORM insert that leaves
# out a NOT NULL column with no DB default fails.
#
# Needs a real database, so it is skipped unless pointed at a SCRATCH one, which it
# migrates first:
#   SCHEMA_TEST_DATABASE_URL=postgresql://lap:lap@database:5432/lc_schema_test python -m pytest test_schema_matches_model.py
import os

import pytest
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

import model  # noqa: F401  (registers every table on SQLModel.metadata)
from migrate import migrate, migrations_folder

URL = os.environ.get('SCHEMA_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='SCHEMA_TEST_DATABASE_URL not set')


@pytest.fixture(scope='module')
def db():
    engine = create_engine(URL)
    migrate(engine, migrations_folder())
    return inspect(engine)


def model_tables():
    return SQLModel.metadata.tables.values()


def test_every_model_table_exists(db):
    missing = {t.name for t in model_tables()} - set(db.get_table_names())
    assert not missing


def test_every_model_column_exists(db):
    missing = [f"{t.name}.{c.name}" for t in model_tables()
               for c in t.columns
               if c.name not in {col['name'] for col in db.get_columns(t.name)}]
    assert not missing


def test_every_required_db_column_is_required_in_the_model(db):
    """A NOT NULL column with no DB default must be in the model and not Optional, or an
    ORM insert can leave it NULL."""
    problems = []
    for t in model_tables():
        for col in db.get_columns(t.name):
            if col['nullable'] or col['default'] is not None:
                continue
            mapped = t.columns.get(col['name'])
            if mapped is None:
                problems.append(f"{t.name}.{col['name']}: not in model.py")
            elif mapped.nullable and not mapped.primary_key:
                problems.append(f"{t.name}.{col['name']}: Optional in model.py, NOT NULL in the schema")
    assert not problems
