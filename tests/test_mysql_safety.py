"""Fail-closed target/reset safeguards; every connector and script is mocked."""

from unittest.mock import MagicMock, patch

import pytest

from tests import mysql_support as support


@pytest.fixture(autouse=True)
def safe_environment(monkeypatch):
    monkeypatch.setattr(support, 'load_dotenv', lambda: None)
    monkeypatch.setenv('CLINIQ_TEST_DATABASE', support.TEST_DATABASE)
    monkeypatch.setenv('CLINIQ_TEST_RESET_CONFIRM', support.TEST_DATABASE)
    monkeypatch.setenv('MYSQL_DATABASE', 'cliniq_db')
    monkeypatch.delenv('CLINIQ_TEST_SQL_EXTENSIONS', raising=False)


@pytest.mark.parametrize('target', ['', 'cliniq_db', 'ventes', 'Hollywood', 'other_existing_db',
                                    'cliniq_test_dev_backup', 'CLINIQ_TEST_DEV', 'cliniq_test_dev; DROP DATABASE cliniq_db'])
def test_rejects_every_unapproved_target_before_connect(monkeypatch, target):
    monkeypatch.setenv('CLINIQ_TEST_DATABASE', target)
    with patch('tests.mysql_support.mysql.connector.connect') as connect:
        with pytest.raises(support.TestDatabaseSafetyError):
            support.DedicatedDatabase()
    connect.assert_not_called()


@pytest.mark.parametrize('confirmation', ['', '1', 'yes', 'cliniq_db'])
def test_exact_reset_confirmation_required(monkeypatch, confirmation):
    monkeypatch.setenv('CLINIQ_TEST_RESET_CONFIRM', confirmation)
    with patch('tests.mysql_support.mysql.connector.connect') as connect:
        with pytest.raises(support.TestDatabaseSafetyError):
            support.DedicatedDatabase()
    connect.assert_not_called()


def test_refuses_application_target_alias(monkeypatch):
    monkeypatch.setenv('MYSQL_DATABASE', 'CLINIQ_TEST_DEV')
    with pytest.raises(support.TestDatabaseSafetyError):
        support.verify_environment()


def reset_connection(*, actual='cliniq_test_dev', objects=(), foreign_keys=0,
                     triggers=0, routines=0, events=0, fk_checks=1):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [(actual,), (fk_checks,), (foreign_keys,), (routines,), (events,)]
    trigger_rows = [('unexpected_trigger','PATIENT','BEFORE','INSERT')] if triggers else []
    cursor.fetchall.side_effect = [objects, trigger_rows]
    return connection, cursor


@pytest.mark.parametrize('reason,kwargs', [
    ('wrong session database', {'actual': 'cliniq_db'}),
    ('unexpected table', {'objects': [('user_documents', 'BASE TABLE')]}),
    ('unexpected view', {'objects': [('PATIENT', 'VIEW')]}),
    ('cross-schema FK', {'foreign_keys': 1}),
    ('trigger', {'triggers': 1}),
    ('routine', {'routines': 1}),
    ('event', {'events': 1}),
    ('FK checks disabled', {'fk_checks': 0}),
])
def test_reset_guards_precede_all_destructive_sql(reason, kwargs):
    connection, cursor = reset_connection(**kwargs)
    with patch('tests.mysql_support.run_script') as run:
        with pytest.raises(support.TestDatabaseSafetyError):
            support.reset_schema(connection)
    assert not any('DROP ' in call.args[0] for call in cursor.execute.call_args_list)
    run.assert_not_called()


def test_reset_only_drops_qualified_approved_tables_then_loads_official_assets():
    connection, cursor = reset_connection(objects=[(name, 'BASE TABLE') for name in support.TABLES])
    with patch('tests.mysql_support.run_script') as run:
        support.reset_schema(connection)
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    drops = [sql for sql in statements if sql.startswith('DROP')]
    assert drops == [f'DROP TABLE IF EXISTS `cliniq_test_dev`.`{name}`' for name in reversed(support.TABLES)]
    assert not any('DROP DATABASE' in sql or 'CREATE DATABASE' in sql or 'FOREIGN_KEY_CHECKS=' in sql.upper() for sql in statements)
    assert [call.args[1] for call in run.call_args_list] == ['01_schema.sql', '02_seed.sql']
    connection.commit.assert_called_once()


def test_guard_is_rechecked_if_confirmation_is_removed(monkeypatch):
    connection, cursor = reset_connection()
    monkeypatch.delenv('CLINIQ_TEST_RESET_CONFIRM')
    with pytest.raises(support.TestDatabaseSafetyError):
        support.reset_schema(connection)
    cursor.execute.assert_not_called()


def test_connect_is_pinned_even_if_option_source_contains_another_database():
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ('cliniq_test_dev',)
    with patch('tests.mysql_support.connection_options', return_value={'database': 'Hollywood'}), \
         patch('tests.mysql_support.mysql.connector.connect', return_value=connection) as connect:
        support.DedicatedDatabase().connect()
    assert connect.call_args.kwargs['database'] == 'cliniq_test_dev'


def test_connect_closes_if_server_selects_wrong_database():
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ('ventes',)
    with patch('tests.mysql_support.connection_options', return_value={}), \
         patch('tests.mysql_support.mysql.connector.connect', return_value=connection):
        with pytest.raises(support.TestDatabaseSafetyError):
            support.DedicatedDatabase().connect()
    connection.close.assert_called_once()


def test_busy_database_never_resets():
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (0,)
    with patch('tests.mysql_support.connection_options', return_value={}), \
         patch.object(support.DedicatedDatabase, 'connect', return_value=connection), \
         patch('tests.mysql_support.reset_schema') as reset:
        with pytest.raises(support.TestDatabaseSafetyError):
            with support.DedicatedDatabase().prepared():
                pass
    reset.assert_not_called()
    connection.close.assert_called_once()


def test_prepared_restores_seed_after_test_exception_and_releases_lock():
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
    with patch('tests.mysql_support.connection_options', return_value={}), \
         patch.object(support.DedicatedDatabase, 'connect', return_value=connection), \
         patch('tests.mysql_support.reset_schema') as reset:
        with pytest.raises(RuntimeError):
            with support.DedicatedDatabase().prepared():
                raise RuntimeError('simulated test failure')
    assert reset.call_count == 2
    connection.close.assert_called_once()
    assert any('RELEASE_LOCK' in call.args[0] for call in connection.cursor.return_value.__enter__.return_value.execute.call_args_list)


@pytest.mark.parametrize('target', [None, 'cliniq_db', 'ventes', 'Hollywood', 'another_existing_db'])
def test_suite_guard_blocks_unmocked_application_connections(target):
    import mysql.connector
    options = {} if target is None else {'database': target}
    with pytest.raises(support.TestDatabaseSafetyError):
        mysql.connector.connect(**options)


@pytest.mark.parametrize('trigger_rows', [
    [('unexpected_trigger','CONSULTATION','BEFORE','INSERT')],
    [('trg_consultation_rdv_bi','PATIENT','BEFORE','INSERT')],
    [('trg_consultation_rdv_bi','CONSULTATION','AFTER','INSERT')],
])
def test_only_exact_owned_trigger_shapes_can_be_reset(trigger_rows):
    connection,cursor=reset_connection()
    cursor.fetchall.side_effect=[[],trigger_rows]
    with pytest.raises(support.TestDatabaseSafetyError):
        support.reset_schema(connection)
    assert not any('DROP ' in call.args[0] for call in cursor.execute.call_args_list)


def test_optional_extensions_load_only_approved_scripts_after_seed(monkeypatch):
    connection,cursor=reset_connection()
    cursor.fetchall.side_effect=[[],[(name,*shape) for name,shape in support.DEV008_TRIGGERS.items()]]
    monkeypatch.setenv('CLINIQ_TEST_SQL_EXTENSIONS','1')
    with patch('tests.mysql_support.run_script') as run:
        support.reset_schema(connection)
    assert [call.args[1] for call in run.call_args_list]==['01_schema.sql','02_seed.sql','03_triggers.sql','05_indexes.sql']
