import json
import logging
import time
import uuid
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from . import metrics
from .config import settings
from .db import check_db_health, get_conn
from .embeddings import embed_text
from .generation import check_ollama_health, generate_answer, stream_answer
from .logging_config import configure_logging, request_id_var

configure_logging(settings.log_level)
logger = logging.getLogger("reposrag.api")

app = FastAPI(title="ReposRAG", version="1.0.0")

# Expose /metrics for Prometheus to scrape.
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["x-request-id"] = request_id
    return response


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    repo: Optional[str] = Field(default=None, description="Optional repo filter")
    top_k: Optional[int] = Field(default=None, ge=1, le=20)


class SourceChunk(BaseModel):
    repo: str
    file_path: str
    chunk_index: int
    similarity: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]
    timings_seconds: dict


# Added for GET /repos api as per Jira Ticket RAG-14
class RepoInfo(BaseModel):
    repo: str
    chunk_count: int
    last_ingested: datetime


# Added for GET /repos api as per Jira Ticket RAG-14
class RepoListResponse(BaseModel):
    repos: List[RepoInfo]


# Added for DELETE /repos/{repo_name} api as per Jira Ticket RAG-15
class DeleteRepoResponse(BaseModel):
    repo: str
    deleted_chunks: int


@app.get("/health")
def health():
    db_ok = check_db_health()
    ollama_ok = check_ollama_health()
    status = "ok" if (db_ok and ollama_ok) else "degraded"
    return {"status": status, "db": db_ok, "ollama": ollama_ok}


# Refactored out of /query as per Jira Ticket RAG-16, so /query and /query/stream share one retrieval path
def _retrieve(req: QueryRequest, top_k: int):
    """Embed the question and retrieve the top-k similar chunks. Shared by /query and /query/stream."""
    logger.info("query.start", extra={"repo": req.repo, "top_k": top_k})

    # --- 1. Embed the question ---
    embed_start = time.perf_counter()
    try:
        query_vec = embed_text(req.question)
    except Exception as e:
        metrics.QUERY_ERRORS.labels(stage="embedding").inc()
        logger.error("query.embedding_failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")
    embed_seconds = time.perf_counter() - embed_start
    metrics.EMBEDDING_LATENCY.observe(embed_seconds)

    # --- 2. Retrieve similar chunks from pgvector ---
    retrieval_start = time.perf_counter()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if req.repo:
                    cur.execute(
                        """
                        SELECT repo, file_path, chunk_index, content,
                               1 - (embedding <=> %s) AS similarity
                        FROM chunks
                        WHERE repo = %s
                        ORDER BY embedding <=> %s
                        LIMIT %s;
                        """,
                        (query_vec, req.repo, query_vec, top_k),
                    )
                else:
                    cur.execute(
                        """
                        SELECT repo, file_path, chunk_index, content,
                               1 - (embedding <=> %s) AS similarity
                        FROM chunks
                        ORDER BY embedding <=> %s
                        LIMIT %s;
                        """,
                        (query_vec, query_vec, top_k),
                    )
                rows = cur.fetchall()
    except Exception as e:
        metrics.QUERY_ERRORS.labels(stage="retrieval").inc()
        logger.error("query.retrieval_failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")
    retrieval_seconds = time.perf_counter() - retrieval_start
    metrics.RETRIEVAL_LATENCY.observe(retrieval_seconds)

    if not rows:
        logger.warning("query.no_results", extra={"repo": req.repo})
        raise HTTPException(status_code=404, detail="No indexed content found. Run ingestion first.")

    metrics.TOP1_SIMILARITY.observe(float(rows[0][4]))

    context_chunks = [
        {"repo": r[0], "file_path": r[1], "chunk_index": r[2], "content": r[3]} for r in rows
    ]
    sources = [
        SourceChunk(repo=r[0], file_path=r[1], chunk_index=r[2], similarity=float(r[4])) for r in rows
    ]
    return context_chunks, sources, embed_seconds, retrieval_seconds, float(rows[0][4])


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    metrics.QUERY_COUNT.inc()
    top_k = req.top_k or settings.top_k

    context_chunks, sources, embed_seconds, retrieval_seconds, top1_similarity = _retrieve(req, top_k)

    # --- 3. Generate answer via Ollama ---
    try:
        answer, generation_seconds = generate_answer(req.question, context_chunks)
    except httpx.TimeoutException:
        metrics.OLLAMA_TIMEOUTS.inc()
        metrics.QUERY_ERRORS.labels(stage="generation").inc()
        logger.error("query.generation_timeout")
        raise HTTPException(status_code=504, detail="Ollama generation timed out.")
    except Exception as e:
        metrics.QUERY_ERRORS.labels(stage="generation").inc()
        logger.error("query.generation_failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")
    metrics.GENERATION_LATENCY.observe(generation_seconds)

    logger.info(
        "query.complete",
        extra={
            "repo": req.repo,
            "embedding_seconds": round(embed_seconds, 4),
            "retrieval_seconds": round(retrieval_seconds, 4),
            "generation_seconds": round(generation_seconds, 4),
            "top1_similarity": top1_similarity,
        },
    )

    return QueryResponse(
        answer=answer,
        sources=sources,
        timings_seconds={
            "embedding": round(embed_seconds, 4),
            "retrieval": round(retrieval_seconds, 4),
            "generation": round(generation_seconds, 4),
        },
    )

# Added for /query/stream api as per Jira Ticket RAG-16
@app.post("/query/stream")
def query_stream(req: QueryRequest):
    """
    Same as /query, but streams the answer over Server-Sent Events as it's
    generated. Emits `token` events during generation, then a single `done`
    event carrying sources and timings once generation completes.
    """
    metrics.QUERY_COUNT.inc()
    top_k = req.top_k or settings.top_k

    context_chunks, sources, embed_seconds, retrieval_seconds, top1_similarity = _retrieve(req, top_k)

    def event_stream():
        generation_start = time.perf_counter()
        try:
            for token in stream_answer(req.question, context_chunks):
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
        except httpx.TimeoutException:
            metrics.OLLAMA_TIMEOUTS.inc()
            metrics.QUERY_ERRORS.labels(stage="generation").inc()
            logger.error("query.generation_timeout")
            yield f"event: error\ndata: {json.dumps({'detail': 'Ollama generation timed out.'})}\n\n"
            return
        except Exception as e:
            metrics.QUERY_ERRORS.labels(stage="generation").inc()
            logger.error("query.generation_failed", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'detail': f'Generation failed: {e}'})}\n\n"
            return

        generation_seconds = time.perf_counter() - generation_start
        metrics.GENERATION_LATENCY.observe(generation_seconds)

        logger.info(
            "query.complete",
            extra={
                "repo": req.repo,
                "embedding_seconds": round(embed_seconds, 4),
                "retrieval_seconds": round(retrieval_seconds, 4),
                "generation_seconds": round(generation_seconds, 4),
                "top1_similarity": top1_similarity,
                "stream": True,
            },
        )

        done_payload = {
            "sources": [s.model_dump() for s in sources],
            "timings_seconds": {
                "embedding": round(embed_seconds, 4),
                "retrieval": round(retrieval_seconds, 4),
                "generation": round(generation_seconds, 4),
            },
        }
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# Added for /repos api as per Jira Ticket RAG-14
@app.get("/repos", response_model=RepoListResponse)
def list_repos():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT repo, COUNT(*), MAX(created_at)
                FROM chunks
                GROUP BY repo
                ORDER BY repo;
                """
            )
            rows = cur.fetchall()
    logger.info("repos.list", extra={"repo_count": len(rows)})
    return RepoListResponse(
        repos=[RepoInfo(repo=r[0], chunk_count=r[1], last_ingested=r[2]) for r in rows]
    )

# Added for /repos/{repo_name} api as per Jira Ticket RAG-15
@app.delete("/repos/{repo_name}", response_model=DeleteRepoResponse)
def delete_repo(repo_name: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE repo = %s;", (repo_name,))
            deleted = cur.rowcount
    if deleted == 0:
        logger.warning("repos.delete_unknown", extra={"repo": repo_name})
        raise HTTPException(status_code=404, detail=f"Unknown repo '{repo_name}'.")
    logger.info("repos.delete", extra={"repo": repo_name, "deleted_chunks": deleted})
    return DeleteRepoResponse(repo=repo_name, deleted_chunks=deleted)