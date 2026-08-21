"""
ReposRAG ingestion CLI.

Usage:
    python -m ingestion.ingest --source local --path /path/to/repo --repo-name clockwise
    python -m ingestion.ingest --source git --url https://github.com/user/repo.git --repo-name pickle-rick

Re-running for the same --repo-name replaces its existing chunks (idempotent).
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List

sys.path.append(str(Path(__file__).resolve().parent.parent))

from api.chunker import chunk_markdown  # noqa: E402
from api.db import get_conn  # noqa: E402
from api.embeddings import embed_batch  # noqa: E402

TARGET_GLOBS = ["README.md", "readme.md", "docs/**/*.md", "CONTRIBUTING.md"]


def find_doc_files(root: Path) -> List[Path]:
    found = set()
    for pattern in TARGET_GLOBS:
        found.update(root.glob(pattern))
    return sorted(found)


def clone_repo(url: str) -> Path:
    import git  # GitPython

    tmp_dir = Path(tempfile.mkdtemp(prefix="reposrag_clone_"))
    print(f"Cloning {url} into {tmp_dir} ...")
    git.Repo.clone_from(url, tmp_dir, depth=1)
    return tmp_dir


def delete_existing_chunks(repo_name: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE repo = %s;", (repo_name,))
    print(f"Cleared existing chunks for repo '{repo_name}'.")


def insert_chunks(repo_name: str, file_path: str, chunks, embeddings):
    with get_conn() as conn:
        with conn.cursor() as cur:
            for chunk, vec in zip(chunks, embeddings):
                cur.execute(
                    """
                    INSERT INTO chunks (repo, file_path, chunk_index, heading_context,
                                         content, token_count, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (repo, file_path, chunk_index)
                    DO UPDATE SET content = EXCLUDED.content,
                                  heading_context = EXCLUDED.heading_context,
                                  token_count = EXCLUDED.token_count,
                                  embedding = EXCLUDED.embedding;
                    """,
                    (
                        repo_name,
                        file_path,
                        chunk.chunk_index,
                        chunk.heading_context,
                        chunk.content,
                        chunk.token_count,
                        vec,
                    ),
                )


def ingest_repo(root: Path, repo_name: str):
    doc_files = find_doc_files(root)
    if not doc_files:
        print(f"No documentation files found under {root} matching {TARGET_GLOBS}")
        return

    delete_existing_chunks(repo_name)

    total_chunks = 0
    for doc_file in doc_files:
        rel_path = str(doc_file.relative_to(root))
        text = doc_file.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_markdown(text)
        if not chunks:
            continue

        print(f"  {rel_path}: {len(chunks)} chunk(s)")
        embeddings = embed_batch([c.content for c in chunks])
        insert_chunks(repo_name, rel_path, chunks, embeddings)
        total_chunks += len(chunks)

    print(f"Done. Ingested {total_chunks} chunks for repo '{repo_name}'.")


def main():
    parser = argparse.ArgumentParser(description="Ingest repo docs into ReposRAG.")
    parser.add_argument("--source", choices=["local", "git"], required=True)
    parser.add_argument("--path", help="Local path to the repo (required if --source local)")
    parser.add_argument("--url", help="Git URL to clone (required if --source git)")
    parser.add_argument("--repo-name", required=True, help="Logical name to store chunks under")
    args = parser.parse_args()

    cleanup_dir = None
    try:
        if args.source == "local":
            if not args.path:
                parser.error("--path is required when --source local")
            root = Path(args.path).resolve()
        else:
            if not args.url:
                parser.error("--url is required when --source git")
            root = clone_repo(args.url)
            cleanup_dir = root

        ingest_repo(root, args.repo_name)
    finally:
        if cleanup_dir and cleanup_dir.exists():
            shutil.rmtree(cleanup_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
