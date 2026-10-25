import pytest

from migrate import Migration, MigrationError, load_migrations, migrations_folder, plan


def m(version, checksum='c'):
    return Migration(version, checksum, '')


def test_a_fresh_database_gets_every_migration_in_order():
    migrations = [m('001-a.sql'), m('002-b.sql')]
    assert plan(migrations, {}) == migrations


def test_applied_migrations_are_skipped():
    assert plan([m('001-a.sql'), m('002-b.sql')], {'001-a.sql': 'c'}) == [m('002-b.sql')]


def test_an_up_to_date_database_has_nothing_to_do():
    assert plan([m('001-a.sql')], {'001-a.sql': 'c'}) == []


def test_editing_an_applied_migration_fails():
    with pytest.raises(MigrationError, match='has changed'):
        plan([m('001-a.sql', 'edited')], {'001-a.sql': 'c'})


def test_a_database_migrated_by_newer_code_fails():
    with pytest.raises(MigrationError, match="doesn't know about"):
        plan([m('001-a.sql')], {'001-a.sql': 'c', '002-b.sql': 'c'})


def test_a_migration_numbered_below_an_applied_one_fails():
    """It would be applied out of order, after a schema that was built without it."""
    with pytest.raises(MigrationError, match='numbered below'):
        plan([m('001-a.sql'), m('002-b.sql'), m('003-c.sql')],
             {'001-a.sql': 'c', '003-c.sql': 'c'})


def test_a_misnamed_file_is_an_error_not_silently_skipped(tmp_path):
    (tmp_path / '001-ok.sql').write_text('SELECT 1;')
    (tmp_path / 'oops.sql').write_text('SELECT 1;')
    with pytest.raises(MigrationError, match='oops.sql'):
        load_migrations(tmp_path)


def test_two_files_with_one_number_is_an_error(tmp_path):
    (tmp_path / '001-a.sql').write_text('SELECT 1;')
    (tmp_path / '001-b.sql').write_text('SELECT 2;')
    with pytest.raises(MigrationError, match='share the number'):
        load_migrations(tmp_path)


def test_the_checksum_follows_the_file_content(tmp_path):
    path = tmp_path / '001-a.sql'
    path.write_text('SELECT 1;')
    before = load_migrations(tmp_path)[0].checksum
    path.write_text('SELECT 2;')
    assert load_migrations(tmp_path)[0].checksum != before


def test_the_repo_migrations_load():
    """Catches a misnamed or duplicate-numbered file in database/migrations/ itself."""
    migrations = load_migrations(migrations_folder())
    assert migrations[0].version == '001-baseline.sql'
