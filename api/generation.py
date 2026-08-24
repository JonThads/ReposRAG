import json
import logging
import time
from typing import List, Tuple

import httpx

from . import metrics
from .config import settings

logger = logging.getLogger("reposrag.generation")

# Added for retry/backoff as per Jira Ticket RAG-8. These are the failure
# modes a retry can plausibly fix — a genuine 4xx/5xx from Ollama itself is
# not retried.
_RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)

SYSTEM_PROMPT = (
    "You are a documentation assistant. Answer the user's question using ONLY "
    "the provided context excerpts. If the answer is not contained in the "
    "context, say clearly that you don't have enough information — do not "
    "guess or use outside knowledge. Cite which source(s) you used by their "
    "[repo/file] label when relevant."
)

def build_prompt(question: str, context_chunks: List[dict]) -> str:
    context_blocks = []
    for c in context_chunks:
        label = f"[{c['repo']}/{c['file_path']}#{c['chunk_index']}]"
        context_blocks.append(f"{label}\n{c['content']}")
    context_text = "\n\n---\n\n".join(context_blocks)

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"### Context\n{context_text}\n\n"
        f"### Question\n{question}\n\n"
        f"### Answer\n"
    )

def generate_answer(question: str, context_chunks: List[dict], timeout: float = 60.0) -> Tuple[str, float]:
    """
    Call the local Ollama server to generate an answer grounded in context_chunks.
    Returns (answer_text, generation_seconds).

    Retries up to `settings.ollama_max_retries` times, with exponential
    backoff, on transient connection errors and timeouts (RAG-8). A genuine
    HTTP error status from Ollama itself is not retried.
    """
    prompt = build_prompt(question, context_chunks)

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }

    attempt = 0
    while True:
        try:
            with httpx.Client(timeout=timeout) as client:
                start = time.perf_counter()
                response = client.post(f"{settings.ollama_host}/api/generate", json=payload)
                response.raise_for_status()
                elapsed = time.perf_counter() - start
            data = response.json()
            return data.get("response", "").strip(), elapsed
        except _RETRYABLE_EXCEPTIONS as e:
            if attempt >= settings.ollama_max_retries:
                raise
            attempt += 1
            metrics.OLLAMA_RETRIES.inc()
            backoff = settings.ollama_retry_backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "ollama.retry",
                extra={"attempt": attempt, "max_retries": settings.ollama_max_retries, "error": str(e), "backoff_seconds": backoff},
            )
            time.sleep(backoff)

# Added for /query/stream api as per Jira Ticket RAG-16
def stream_answer(question: str, context_chunks: List[dict], timeout: float = 60.0):
    """
    Call Ollama with stream=True and yield answer tokens as they arrive.
    Caller is responsible for framing each token.
    """
    prompt = build_prompt(question, context_chunks)

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": True,
    }

    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", f"{settings.ollama_host}/api/generate", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("response", "")
                if token:
                    yield token
                if data.get("done"):
                    break

def check_ollama_health(timeout: float = 5.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{settings.ollama_host}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False