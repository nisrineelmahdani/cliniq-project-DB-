"""Provision only a new CLINIQ database; never reset, reuse or drop a database.

Run ``python -m database.setup``. Integration tests use the same scripts but
separate credentials and the explicitly authorized cliniq_test_dev database.
"""

import argparse
import os
from pathlib import Path
import re
from uuid import uuid4
from typing import cast
from mysql.connector.connection import MySQLConnection

from dotenv import load_dotenv
import mysql.connector


SQL_DIRECTORY = Path(__file__).resolve().parent


def connection_options(kind: str) -> dict:
    """Read explicit setup/test credentials, never the application's MYSQL_* DB."""
    if kind not in {"dev", "test"}:
        raise ValueError("Expected dev or test")
    load_dotenv()
    prefix = "CLINIQ_SETUP_" if kind == "dev" else "CLINIQ_TEST_"
    user = os.getenv(prefix + "USER")
    if not user:
        raise ValueError(f"Set {prefix}USER before provisioning a new database")
    port = int(os.getenv(prefix + "PORT", "3306"))
    if not 1 <= port <= 65535:
        raise ValueError(f"{prefix}PORT must be between 1 and 65535")
    options = {
        "host": os.getenv(prefix + "HOST", "127.0.0.1"),
        "port": port,
        "user": user,
        "password": os.getenv(prefix + "PASSWORD", ""),
        "connection_timeout": 5,
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if os.getenv(prefix + "UNIX_SOCKET"):
        options["unix_socket"] = os.environ[prefix + "UNIX_SOCKET"]
    return options


def run_script(connection, filename: str) -> None:
    """Consume every result so later-statement errors cannot be missed.

    Connector/Python >= 9.2 supplies the public multi-statement execution API.
    On any seed failure the caller rolls back instead of continuing to COMMIT.
    """
    with connection.cursor() as cursor:
        cursor.execute((SQL_DIRECTORY / filename).read_text(encoding="utf-8"), map_results=True)
        while cursor.nextset():
            pass


def provision(kind: str) -> str:
    """Return the name of a newly created database, retaining it for inspection.

    CREATE DATABASE intentionally has no IF NOT EXISTS. Even a UUID collision
    stops execution before the schema is touched. MySQL DDL is not transactional;
    a failed run is retained and a later run always creates a different database.
    """
    options = connection_options(kind)
    name = f"cliniq_{kind}_{uuid4().hex}"
    connection = cast(MySQLConnection, mysql.connector.connect(**options))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cast(tuple[str], cursor.fetchone())[0]
            parsed = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
            if (not parsed or 'mariadb' in version.lower()
                    or tuple(map(int, parsed.groups())) < (8, 0, 16)
                    or int(parsed.group(1)) != 8):
                raise ValueError("MySQL 8.0.16+ (8.x) is required for enforced CHECK constraints")
            cursor.execute("SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")
            # name is generated here, never supplied by a user or environment.
            cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        print(f"Created dedicated database: {name}", flush=True)
        connection.database = name
        run_script(connection, "01_schema.sql")
        run_script(connection, "02_seed.sql")
        connection.commit()
        return name
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("dev", "test"), default="dev")
    args = parser.parse_args()
    try:
        name = provision(args.kind)
    except (ValueError, mysql.connector.Error) as exc:
        # Connector messages are not printed: they can contain connection details.
        raise SystemExit(f"Setup failed ({type(exc).__name__}). Check credentials, MySQL version and SQL files. Any created database was retained.") from None
    print(f"Schema and seed loaded. Database retained: {name}")
    if args.kind == "dev":
        print(f"To use it in CLINIQ, set MYSQL_DATABASE={name} in .env.")


if __name__ == "__main__":
    main()
