"""Fail-closed integration harness for the explicitly provisioned test database.

No CREATE DATABASE, DROP DATABASE, USE or foreign-key disabling is issued here.
Every reset requires an exact database name and an explicit confirmation token.
"""

from contextlib import contextmanager
import os

import mysql.connector
from dotenv import load_dotenv

from database.setup import connection_options, run_script


TEST_DATABASE = 'cliniq_test_dev'
LOCK_NAME = 'cliniq_test_dev.integration_tests'
DEV008_TRIGGERS = {
    'trg_consultation_rdv_bi': ('CONSULTATION','BEFORE','INSERT'),
    'trg_consultation_rdv_bu': ('CONSULTATION','BEFORE','UPDATE'),
    'trg_rdv_consultation_bu': ('RENDEZ_VOUS','BEFORE','UPDATE'),
}
# Parent-first order matches the approved schema; reverse order is FK-safe reset.
TABLES = (
    'SERVICE', 'SPECIALITE', 'MEDECIN', 'EXERCER', 'PATIENT', 'RENDEZ_VOUS',
    'SALLE', 'CONSULTATION', 'MEDICAMENT', 'PRESCRIRE', 'CHAMBRE', 'LIT',
    'HOSPITALISATION', 'ACTE_MEDICAL', 'DESIGNER_RESPONSABLE',
)
STRICT_MODE = ('STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,'
               'ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION')


class TestDatabaseSafetyError(RuntimeError):
    """Refuse a test operation before any destructive SQL."""


# Prevent pytest from trying to collect the exception as a test class.
setattr(TestDatabaseSafetyError, '__test__', False)


def verify_environment() -> None:
    load_dotenv()
    if os.getenv('CLINIQ_TEST_DATABASE') != TEST_DATABASE:
        raise TestDatabaseSafetyError('CLINIQ_TEST_DATABASE must be exactly cliniq_test_dev.')
    if os.getenv('CLINIQ_TEST_RESET_CONFIRM') != TEST_DATABASE:
        raise TestDatabaseSafetyError('Explicit reset confirmation required: CLINIQ_TEST_RESET_CONFIRM=cliniq_test_dev.')
    if os.getenv('MYSQL_DATABASE', '').casefold() == TEST_DATABASE:
        raise TestDatabaseSafetyError('The application database must not be the dedicated test database.')


def verify_selected_database(connection) -> None:
    # Recheck actual server selection, not merely connection options.
    with connection.cursor() as cursor:
        cursor.execute('SELECT DATABASE()')
        if cursor.fetchone()[0] != TEST_DATABASE:
            raise TestDatabaseSafetyError('The server selected an unauthorized database; refusing test access.')


def verify_reset(connection) -> None:
    """Inspect all guards before the first DROP TABLE. Never change FK checks."""
    verify_environment()
    verify_selected_database(connection)
    with connection.cursor() as cursor:
        cursor.execute('SELECT @@SESSION.foreign_key_checks')
        if cursor.fetchone()[0] != 1:
            raise TestDatabaseSafetyError('Foreign-key checks must be enabled before any test reset.')
        cursor.execute('SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s', (TEST_DATABASE,))
        objects = cursor.fetchall()
        if any(name not in TABLES or kind != 'BASE TABLE' for name, kind in objects):
            raise TestDatabaseSafetyError('Unexpected test objects found; no tables were reset.')
        # Block incoming AND outgoing cross-database references. Nothing outside
        # cliniq_test_dev may participate in a reset, even with an overprivileged account.
        cursor.execute('''SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
            WHERE REFERENCED_TABLE_SCHEMA IS NOT NULL AND
              ((TABLE_SCHEMA = %s AND REFERENCED_TABLE_SCHEMA <> %s)
               OR (REFERENCED_TABLE_SCHEMA = %s AND TABLE_SCHEMA <> %s))''',
                       (TEST_DATABASE,) * 4)
        if cursor.fetchone()[0]:
            raise TestDatabaseSafetyError('Cross-database foreign keys found; no tables were reset.')
        cursor.execute('SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,ACTION_TIMING,EVENT_MANIPULATION FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = %s', (TEST_DATABASE,))
        if any(DEV008_TRIGGERS.get(name) != (table,timing,event) for name,table,timing,event in cursor.fetchall()):
            raise TestDatabaseSafetyError('Unexpected test triggers found; no tables were reset.')
        for catalog, schema_column in (('ROUTINES', 'ROUTINE_SCHEMA'),
                                       ('EVENTS', 'EVENT_SCHEMA')):
            cursor.execute(f'SELECT COUNT(*) FROM information_schema.{catalog} WHERE {schema_column} = %s', (TEST_DATABASE,))
            if cursor.fetchone()[0]:
                raise TestDatabaseSafetyError('Unexpected executable test objects found; no tables were reset.')


def reset_schema(connection) -> None:
    verify_reset(connection)
    with connection.cursor() as cursor:
        for table in reversed(TABLES):
            # Both identifiers are constants, qualified even if session DB changes.
            cursor.execute(f'DROP TABLE IF EXISTS `{TEST_DATABASE}`.`{table}`')
    run_script(connection, '01_schema.sql')
    run_script(connection, '02_seed.sql')
    if os.getenv('CLINIQ_TEST_SQL_EXTENSIONS') == '1':
        run_script(connection, '03_triggers.sql')
        run_script(connection, '05_indexes.sql')
    connection.commit()


class DedicatedDatabase:
    def __init__(self):
        verify_environment()
        self.options = {**connection_options('test'), 'database': TEST_DATABASE}

    def connect(self):
        verify_environment()
        # The caller cannot override this database with MYSQL_DATABASE or a kwarg.
        connection = mysql.connector.connect(**self.options)
        try:
            verify_selected_database(connection)
            with connection.cursor() as cursor:
                cursor.execute('SET SESSION sql_mode = %s', (STRICT_MODE,))
            connection.rollback()  # metadata checks must not leave an open transaction
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def prepared(self):
        """Serialize modules/runs and restore the seed after committed workflow probes."""
        connection = self.connect()
        locked = False
        prepared = False
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT GET_LOCK(%s, 0)', (LOCK_NAME,))
                if cursor.fetchone()[0] != 1:
                    raise TestDatabaseSafetyError('Another integration run owns cliniq_test_dev; retry after it finishes.')
                locked = True
            reset_schema(connection)
            prepared = True
            yield self
        finally:
            try:
                if prepared:
                    connection.rollback()
                    reset_schema(connection)
            finally:
                try:
                    if locked:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT RELEASE_LOCK(%s)', (LOCK_NAME,))
                            cursor.fetchone()
                finally:
                    connection.close()
