from functools import lru_cache
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import settings

@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Load the embedding model once and cache it for the process lifetime."""
    return SentenceTransformer(settings.embedding_model)

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