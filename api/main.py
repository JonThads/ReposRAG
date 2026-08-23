import logging
import time
import uuid
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from . import metrics
from .config import settings
from .db import check_db_health, get_conn
from .embeddings import embed_text
from .generation import check_ollama_health, generate_answer
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


@app.get("/health")
def health():
    db_ok = check_db_health()
    ollama_ok = check_ollama_health()
    status = "ok" if (db_ok and ollama_ok) else "degraded"
    return {"status": status, "db": db_ok, "ollama": ollama_ok}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    metrics.QUERY_COUNT.inc()
    top_k = req.top_k or settings.top_k
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

    # --- 3. Generate the answer via Ollama ---
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
            "top1_similarity": float(rows[0][4]),
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