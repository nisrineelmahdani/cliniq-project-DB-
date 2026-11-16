"""Short-lived transactions with public, patient-safe error messages."""

from contextlib import contextmanager

import mysql.connector

from db.connection import DatabaseConfigurationError, DatabaseConnectionError, transaction


class RepositoryError(RuntimeError):
    """Safe to display; never carries SQL, credentials or patient values."""


class PatientNotFoundError(RepositoryError):
    """The selected patient no longer exists."""


class ConcurrentEditError(RepositoryError):
    """Another editor changed the patient since this form opened."""


@contextmanager
def database_cursor(*, readonly=False, isolation_level=None):
    """Close cursor/connection and hide connector errors, including on commit.

    Reads use a repeatable-read snapshot so a dashboard or patient detail is
    internally consistent. Writers may explicitly select an isolation level;
    defaults for existing callers are unchanged. No patient rows are cached globally.
    """
    try:
        with transaction() as connection:
            if readonly:
                connection.start_transaction(
                    isolation_level="REPEATABLE READ", consistent_snapshot=True,
                    readonly=True,
                )
            elif isolation_level is not None:
                connection.start_transaction(isolation_level=isolation_level)
            with connection.cursor(dictionary=True) as cursor:
                yield cursor
    except (mysql.connector.Error, DatabaseConfigurationError, DatabaseConnectionError):
        raise RepositoryError(
            "Opération MySQL impossible. Vérifiez la connexion et réessayez."
        ) from None
