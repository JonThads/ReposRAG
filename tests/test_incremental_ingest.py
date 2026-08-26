from unittest.mock import MagicMock, call

from ingestion import ingest


def _fake_conn():
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    return conn, cursor


def test_content_hash_is_stable_sha256():
    assert ingest._content_hash(b"hello") == ingest._content_hash(b"hello")
    assert ingest._content_hash(b"hello") != ingest._content_hash(b"world")


def test_unchanged_file_is_skipped_with_no_embedding_work(tmp_path, monkeypatch):
    doc = tmp_path / "README.md"
    doc.write_text("Hello world.")
    existing_hash = ingest._content_hash(doc.read_bytes())

    conn, cursor = _fake_conn()
    monkeypatch.setattr(ingest, "get_conn", lambda: conn)
    cursor.fetchall.return_value = [("README.md", existing_hash)]

    embed_calls = []
    monkeypatch.setattr(ingest, "embed_batch", lambda texts: embed_calls.append(texts) or [])

    ingest.ingest_repo(tmp_path, "reponame")

    assert embed_calls == []


def test_changed_file_is_rechunked_and_reembedded(tmp_path, monkeypatch):
    doc = tmp_path / "README.md"
    doc.write_text("New content that differs from what was stored.")

    conn, cursor = _fake_conn()
    monkeypatch.setattr(ingest, "get_conn", lambda: conn)
    cursor.fetchall.return_value = [("README.md", "stale-hash-does-not-match")]

    fake_chunks = [ingest.chunk_markdown("New content that differs from what was stored.")[0]]
    monkeypatch.setattr(ingest, "_chunk_file", lambda doc_file, text: fake_chunks)

    embed_calls = []
    monkeypatch.setattr(ingest, "embed_batch", lambda texts: embed_calls.append(texts) or [[0.0]])

    ingest.ingest_repo(tmp_path, "reponame")

    assert len(embed_calls) == 1


def test_deleted_file_has_its_chunks_removed(tmp_path, monkeypatch):
    # Only a hash record exists for "gone.md" — the file itself is absent
    # from tmp_path, simulating a file removed since the last ingest.
    doc = tmp_path / "README.md"
    doc.write_text("Still here.")
    still_here_hash = ingest._content_hash(doc.read_bytes())

    conn, cursor = _fake_conn()
    monkeypatch.setattr(ingest, "get_conn", lambda: conn)
    cursor.fetchall.return_value = [
        ("README.md", still_here_hash),
        ("gone.md", "some-old-hash"),
    ]
    monkeypatch.setattr(ingest, "embed_batch", lambda texts: [])

    ingest.ingest_repo(tmp_path, "reponame")

    deleted_calls = [
        c for c in cursor.execute.call_args_list
        if c == call("DELETE FROM chunks WHERE repo = %s AND file_path = %s;", ("reponame", "gone.md"))
    ]
    assert deleted_calls, "expected chunks for the removed file to be deleted"
