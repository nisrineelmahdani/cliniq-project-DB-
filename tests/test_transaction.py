"""Connection lifecycle guarantees without requiring a live MySQL server."""

from unittest.mock import Mock, patch

import mysql.connector
import pytest

from db.connection import transaction


def test_success_commits_and_closes():
    connection = Mock()
    with patch("db.connection.get_connection", return_value=connection):
        with transaction() as active:
            assert active is connection
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once_with()


@pytest.mark.parametrize("commit_fails", [False, True])
def test_failure_rolls_back_and_closes(commit_fails):
    connection = Mock()
    error = mysql.connector.Error("operation failed")
    if commit_fails:
        connection.commit.side_effect = error
    with patch("db.connection.get_connection", return_value=connection):
        with pytest.raises(mysql.connector.Error) as caught:
            with transaction():
                if not commit_fails:
                    raise error
    assert caught.value is error
    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()
