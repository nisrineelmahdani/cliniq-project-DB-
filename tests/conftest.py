"""Shared fixtures; integration preparation is requested only after explicit opt-in."""

import pytest
import mysql.connector

from tests.mysql_support import DedicatedDatabase, TEST_DATABASE, TestDatabaseSafetyError


@pytest.fixture(scope='module')
def dedicated_mysql_database():
    with DedicatedDatabase().prepared() as database:
        yield database


@pytest.fixture(autouse=True)
def prevent_non_test_mysql_connections(monkeypatch):
    """A forgotten repository mock must fail before connecting to an application DB.

    The module-scoped integration setup has its own identical pinning/checks.
    Unit tests may replace this connector with a mock; no real connection then occurs.
    """
    real_connect = mysql.connector.connect

    def guarded_connect(*args, **kwargs):
        if args or kwargs.get('database') != TEST_DATABASE:
            raise TestDatabaseSafetyError('Real test connections must explicitly select cliniq_test_dev.')
        return real_connect(**kwargs)

    monkeypatch.setattr(mysql.connector, 'connect', guarded_connect)
