from typing import List, Tuple

import httpx
import json

from .config import settings

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
    """
    prompt = build_prompt(question, context_chunks)

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }

    with httpx.Client(timeout=timeout) as client:
        import time

        start = time.perf_counter()
        response = client.post(f"{settings.ollama_host}/api/generate", json=payload)
        response.raise_for_status()
        elapsed = time.perf_counter() - start

    data = response.json()
    return data.get("response", "").strip(), elapsed

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