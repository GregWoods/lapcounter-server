# The ONE thing that builds the database schema (#84). Applies every database/migrations/
# NNN-*.sql file not yet recorded in schema_migrations, in order, each in its own
# transaction. Run by the one-shot `migrate` compose service on every stack start; `api`
# and `dbwriter` wait for it to exit successfully, so neither can touch a database that
# isn't in the expected state.
#
# Nothing else creates tables: not create_all, not a hand-run schema file. There used to
# be three builders and they drifted — a create_all-built driver_laps.created_at had no
# DB default, and dbwriter silently lost every lap.
#
# A migration that has been applied must never be edited: its checksum is recorded, and a
# mismatch fails the run. Change the schema by adding a new numbered file.
#
# Demo data is a separate, optional step - see sampledata.py.

import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import NamedTuple

from sqlmodel import create_engine

MIGRATION_FILE = re.compile(r'^(\d{3})-[a-z0-9-]+\.sql$')
# Any constant will do; it only has to be the same for every concurrent runner.
ADVISORY_LOCK_ID = 840_084
CONNECT_TIMEOUT_S = 120


class Migration(NamedTuple):
    version: str      # the file name, e.g. '001-baseline.sql'
    checksum: str     # sha256 of the file's bytes
    sql: str


class MigrationError(Exception):
    pass


def load_migrations(folder: Path) -> list[Migration]:
    """Every migration file in `folder`, in order. Anything else in the folder that
    ends in .sql is an error rather than silently skipped: a misnamed migration that
    never runs is exactly the kind of drift this exists to prevent."""
    migrations = []
    numbers = set()
    for path in sorted(folder.glob('*.sql')):
        match = MIGRATION_FILE.match(path.name)
        if not match:
            raise MigrationError(f"{path.name}: migrations must be named NNN-lowercase-words.sql")
        if match.group(1) in numbers:
            raise MigrationError(f"{path.name}: two migrations share the number {match.group(1)}")
        numbers.add(match.group(1))
        data = path.read_bytes()
        migrations.append(Migration(path.name, hashlib.sha256(data).hexdigest(), data.decode('utf-8')))
    return migrations


def plan(migrations: list[Migration], applied: dict[str, str]) -> list[Migration]:
    """The migrations still to apply, given `applied` (version -> recorded checksum).
    Pure, so it's unit-tested without a database (test_migrate.py).

    Refuses — rather than guessing — when an applied file has changed, or when the
    database has a migration this code doesn't (it was migrated by a newer image)."""
    by_version = {m.version: m for m in migrations}
    unknown = sorted(set(applied) - set(by_version))
    if unknown:
        raise MigrationError(f"database has migrations this code doesn't know about: {unknown} "
                             f"— it was migrated by a newer version")
    for version, checksum in applied.items():
        if by_version[version].checksum != checksum:
            raise MigrationError(f"{version} has changed since it was applied. Never edit an "
                                 f"applied migration; add a new one")
    pending = [m for m in migrations if m.version not in applied]
    # Applied ones must be a prefix: a gap means a migration was added below one that
    # has already run, and would be applied out of order.
    if pending and any(m.version > pending[0].version for m in migrations if m.version in applied):
        raise MigrationError(f"{pending[0].version} is numbered below a migration that has "
                             f"already been applied; renumber it after the last one")
    return pending


def migrations_folder() -> Path:
    """database/migrations/, in either environment this runs in: a full repo checkout,
    or the api container, where database/ sits beside app/ (mounted read-only in dev,
    copied into the image in prod)."""
    here = Path(__file__).resolve()
    candidates = [here.parents[2] / 'database' / 'migrations',   # repo root (local run)
                  here.parents[1] / 'database' / 'migrations']   # container: beside app/
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise MigrationError(f"no database/migrations folder - tried: {', '.join(map(str, candidates))}")


def create_engine_from_settings():
    """The DB_* variables only — read directly, like dbwriter, rather than through the
    API's Settings, which also demands media settings the migrate service has no use for."""
    env = os.environ
    return create_engine(f"postgresql://{env['DB_USER']}:{env['DB_PASSWORD']}@{env['DB_HOST']}:"
                         f"{env['DB_PORT']}/{env['DB_DATABASE']}")


def _connect(engine):
    """The database container may still be starting when the stack comes up."""
    deadline = time.monotonic() + CONNECT_TIMEOUT_S
    while True:
        try:
            return engine.raw_connection()
        except Exception as e:
            if time.monotonic() > deadline:
                raise
            print(f"database not ready ({e.__class__.__name__}), retrying")
            time.sleep(2)


def migrate(engine, folder: Path) -> list[str]:
    """Apply what's pending. Returns the versions applied."""
    migrations = load_migrations(folder)
    conn = _connect(engine)
    try:
        cur = conn.cursor()
        # Session-level lock, held until this connection closes: two runners starting at
        # once would otherwise both apply the same migration.
        cur.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
        cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
        if not cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
            if cur.fetchone()[0]:
                raise MigrationError(
                    "the database has tables but no schema_migrations: it was built by the old "
                    "schema.sql/create_all builders. There is no real data, so rebuild it: "
                    "DROP SCHEMA public CASCADE; CREATE SCHEMA public; then restart the stack")
            cur.execute("""CREATE TABLE schema_migrations (
                               version TEXT PRIMARY KEY,
                               checksum TEXT NOT NULL,
                               applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        conn.commit()

        cur.execute("SELECT version, checksum FROM schema_migrations")
        applied = dict(cur.fetchall())
        conn.commit()
        done = []
        for m in plan(migrations, applied):
            try:
                cur.execute(m.sql)
                cur.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                            (m.version, m.checksum))
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise MigrationError(f"{m.version} failed, nothing from it was applied: {e}") from e
            print(f"applied {m.version}")
            done.append(m.version)
        return done
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        applied = migrate(create_engine_from_settings(), migrations_folder())
    except MigrationError as e:
        print(f"MIGRATION FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"database up to date ({len(applied)} applied)")
