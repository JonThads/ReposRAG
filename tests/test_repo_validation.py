from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api import main


def _fake_get_conn(fetchone_result, fetchall_result):
    """
    Build a callable matching `get_conn()` whose returned object satisfies
    `with get_conn() as conn: with conn.cursor() as cur: ...`, with `cur`
    pre-configured to return the given fetchone/fetchall results.
    """
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False

    return lambda: conn


def test_validate_repo_passes_silently_when_repo_exists(monkeypatch):
    monkeypatch.setattr(main, "get_conn", _fake_get_conn(fetchone_result=(1,), fetchall_result=[]))

    main._validate_repo("clockwise")  # should not raise


def test_validate_repo_raises_404_listing_known_repos(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_conn",
        _fake_get_conn(fetchone_result=None, fetchall_result=[("clockwise",), ("pickle-rick",)]),
    )

    with pytest.raises(HTTPException) as exc_info:
        main._validate_repo("typo-repo")

    assert exc_info.value.status_code == 404
    assert "typo-repo" in exc_info.value.detail
    assert "clockwise" in exc_info.value.detail
    assert "pickle-rick" in exc_info.value.detail


def test_validate_repo_raises_404_with_empty_index_message(monkeypatch):
    monkeypatch.setattr(main, "get_conn", _fake_get_conn(fetchone_result=None, fetchall_result=[]))

    with pytest.raises(HTTPException) as exc_info:
        main._validate_repo("anything")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No indexed content found. Run ingestion first."
