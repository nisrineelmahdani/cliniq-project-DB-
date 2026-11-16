"""Tests for MySQL connection configuration and availability checks."""

from unittest.mock import Mock, patch

import mysql.connector
import pytest

from db.connection import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    check_database_connection,
    get_connection,
)


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    """Unit tests must not read the developer's real .env or credentials."""
    monkeypatch.setattr("db.connection.load_dotenv", lambda: None)
    monkeypatch.setenv("MYSQL_PORT", "3306")


def _set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_DATABASE", "clinique_test")
    monkeypatch.setenv("MYSQL_USER", "test_user")
    monkeypatch.setenv("MYSQL_PASSWORD", "test_password")


def test_get_connection_uses_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    connection = Mock()

    with patch("db.connection.mysql.connector.connect", return_value=connection) as connect:
        assert get_connection() is connection

    connect.assert_called_once_with(
        host="localhost",
        port=3306,
        database="clinique_test",
        user="test_user",
        password="test_password",
        connection_timeout=5,
    )


def test_get_connection_rejects_missing_required_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYSQL_HOST", raising=False)
    monkeypatch.setenv("MYSQL_DATABASE", "clinique_test")
    monkeypatch.setenv("MYSQL_USER", "test_user")

    with pytest.raises(DatabaseConfigurationError, match="MYSQL_HOST"):
        get_connection()


def test_get_connection_rejects_invalid_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("MYSQL_PORT", "not-a-port")

    with pytest.raises(DatabaseConfigurationError, match="MYSQL_PORT"):
        get_connection()


def test_get_connection_wraps_connector_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)

    with patch(
        "db.connection.mysql.connector.connect",
        side_effect=mysql.connector.Error("connection refused"),
    ):
        with pytest.raises(DatabaseConnectionError) as error:
            get_connection()

    assert isinstance(error.value.__cause__, mysql.connector.Error)


def test_database_check_closes_successful_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    connection = Mock()

    with patch("db.connection.mysql.connector.connect", return_value=connection):
        check_database_connection()

    connection.close.assert_called_once_with()
