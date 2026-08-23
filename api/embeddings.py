import logging
from functools import lru_cache
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import settings

# Added Ollama GPU Support as per Jira Ticket RAG-24
logger = logging.getLogger("reposrag.embeddings")

def resolve_device(requested: str) -> str:
    """Resolve 'auto' to the best available device; pass explicit choices through unchanged."""
    if requested != "auto":
        return requested

    try:
        import torch
    except ImportError:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"

@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Load the embedding model once and cache it for the process lifetime."""
    device = resolve_device(settings.embedding_device)
    logger.info("embeddings.model_load", extra={"model": settings.embedding_model, "device": device})
    return SentenceTransformer(settings.embedding_model, device=device)

def embed_text(text: str) -> np.ndarray:
    """Embed a single string. Returns a 1D float32 numpy array."""
    model = get_embedder()
    vec = model.encode(text, normalize_embeddings=True)
    return np.asarray(vec, dtype=np.float32)

def embed_batch(texts: List[str]) -> np.ndarray:
    """Embed a list of strings. Returns a 2D float32 numpy array (n, dim)."""
    model = get_embedder()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=len(texts) > 20)
    return np.asarray(vecs, dtype=np.float32)