"""Configuration and connection helpers for MySQL."""

import os
from contextlib import contextmanager
from typing import cast
from collections.abc import Iterator

import mysql.connector
from dotenv import load_dotenv
from mysql.connector.connection import MySQLConnection


class DatabaseConfigurationError(ValueError):
    """Raised when required MySQL environment variables are invalid."""


class DatabaseConnectionError(RuntimeError):
    """Raised when a MySQL connection cannot be established or closed."""


def _connection_config() -> dict[str, str | int]:
    load_dotenv()

    required = ("MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_USER")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise DatabaseConfigurationError(
            "Variables d'environnement manquantes : " + ", ".join(missing)
        )

    port_value = os.getenv("MYSQL_PORT", "3306")
    try:
        port = int(port_value)
    except ValueError as exc:
        raise DatabaseConfigurationError(
            "MYSQL_PORT doit être un entier compris entre 1 et 65535."
        ) from exc
    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError(
            "MYSQL_PORT doit être un entier compris entre 1 et 65535."
        )

    return {
        "host": os.environ["MYSQL_HOST"],
        "port": port,
        "database": os.environ["MYSQL_DATABASE"],
        "user": os.environ["MYSQL_USER"],
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "connection_timeout": 5,
    }


def get_connection() -> MySQLConnection:
    """Open and return a MySQL connection using environment configuration."""
    config = _connection_config()
    try:
        return cast(MySQLConnection, mysql.connector.connect(**config))
    except mysql.connector.Error as exc:
        raise DatabaseConnectionError(
            "Impossible d'établir la connexion au serveur MySQL."
        ) from exc


def check_database_connection() -> None:
    """Verify that MySQL accepts a connection, then close it."""
    connection = get_connection()
    try:
        connection.close()
    except mysql.connector.Error as exc:
        raise DatabaseConnectionError(
            "La connexion au serveur MySQL n'a pas pu être fermée proprement."
        ) from exc


@contextmanager
def transaction() -> Iterator[MySQLConnection]:
    """Commit successful work; roll back failures and always close the connection.

    Repositories must bind values with cursor.execute(sql, parameters).
    No schema-dependent operations are defined before the approved SQL is supplied.
    """
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except BaseException:
        try:
            connection.rollback()
        except mysql.connector.Error:
            pass  # Preserve the original operation error.
        raise
    finally:
        connection.close()
