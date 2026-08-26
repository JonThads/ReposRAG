"""
ReposRAG ingestion CLI.

Usage:
    python -m ingestion.ingest --source local --path /path/to/repo --repo-name clockwise
    python -m ingestion.ingest --source git --url https://github.com/user/repo.git --repo-name pickle-rick

Re-running for the same --repo-name replaces its existing chunks (idempotent).
"""

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List

sys.path.append(str(Path(__file__).resolve().parent.parent))

from api.chunker import chunk_code, chunk_markdown  # noqa: E402
from api.db import get_conn  # noqa: E402
from api.embeddings import embed_batch  # noqa: E402
from api.logging_config import configure_logging  # noqa: E402

DOC_GLOBS = ["README.md", "readme.md", "docs/**/*.md", "CONTRIBUTING.md"]
# Added for additional doc formats + source files as per Jira Ticket
# RAG-18. Both are opt-in via --include-code, since both are noisier and
# costlier to embed than the curated doc set above.
EXTRA_DOC_GLOBS = ["**/*.rst", "**/*.txt"]
CODE_GLOBS = ["**/*.py", "**/*.js", "**/*.ts", "**/*.go"]
EXCLUDED_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build",
    ".pytest_cache", ".ruff_cache", ".mypy_cache",
}

logger = logging.getLogger("reposrag.ingest")


def _iter_files(root: Path, globs: List[str]) -> List[Path]:
    found = set()
    for pattern in globs:
        for path in root.glob(pattern):
            if path.is_file() and not any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(root).parts):
                found.add(path)
    return sorted(found)


def find_doc_files(root: Path, include_code: bool = False) -> List[Path]:
    globs = list(DOC_GLOBS) + (EXTRA_DOC_GLOBS if include_code else [])
    return _iter_files(root, globs)


def find_code_files(root: Path) -> List[Path]:
    return _iter_files(root, CODE_GLOBS)


def clone_repo(url: str) -> Path:
    import git  # GitPython

    tmp_dir = Path(tempfile.mkdtemp(prefix="reposrag_clone_"))
    logger.info("ingest.clone_start", extra={"url": url, "tmp_dir": str(tmp_dir)})
    git.Repo.clone_from(url, tmp_dir, depth=1)
    return tmp_dir


def delete_existing_chunks(repo_name: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE repo = %s;", (repo_name,))
    logger.info("ingest.cleared_existing_chunks", extra={"repo": repo_name})


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


def _chunk_file(doc_file: Path, text: str):
    ext = doc_file.suffix.lower()
    if ext in (".py", ".js", ".ts", ".go"):
        return chunk_code(text, ext)
    return chunk_markdown(text)


def ingest_repo(root: Path, repo_name: str, include_code: bool = False):
    doc_files = find_doc_files(root, include_code=include_code)
    if include_code:
        doc_files += find_code_files(root)
    if not doc_files:
        logger.warning("ingest.no_doc_files", extra={"root": str(root), "include_code": include_code})
        return

    delete_existing_chunks(repo_name)

    total_chunks = 0
    for doc_file in doc_files:
        rel_path = str(doc_file.relative_to(root))
        text = doc_file.read_text(encoding="utf-8", errors="ignore")
        chunks = _chunk_file(doc_file, text)
        if not chunks:
            continue

        logger.info("ingest.file_chunked", extra={"file": rel_path, "chunk_count": len(chunks)})
        embeddings = embed_batch([c.content for c in chunks])
        insert_chunks(repo_name, rel_path, chunks, embeddings)
        total_chunks += len(chunks)

    logger.info("ingest.complete", extra={"repo": repo_name, "total_chunks": total_chunks})


def main():
    configure_logging()
    parser = argparse.ArgumentParser(description="Ingest repo docs into ReposRAG.")
    parser.add_argument("--source", choices=["local", "git"], required=True)
    parser.add_argument("--path", help="Local path to the repo (required if --source local)")
    parser.add_argument("--url", help="Git URL to clone (required if --source git)")
    parser.add_argument("--repo-name", required=True, help="Logical name to store chunks under")
    parser.add_argument(
        "--include-code",
        action="store_true",
        help="Also ingest source files (.py/.js/.ts/.go) and extra doc formats (.rst/.txt).",
    )
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

        ingest_repo(root, args.repo_name, include_code=args.include_code)
    finally:
        if cleanup_dir and cleanup_dir.exists():
            shutil.rmtree(cleanup_dir, ignore_errors=True)


if __name__ == "__main__":
    main()