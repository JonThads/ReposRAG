from dataclasses import dataclass
from typing import List, Optional

import tiktoken

from .config import settings

_ENCODING = tiktoken.get_encoding("cl100k_base")

@dataclass
class Chunk:
    content: str
    chunk_index: int
    token_count: int
    heading_context: Optional[str] = None

def _split_into_paragraphs(text: str) -> List[str]:
    """Split on blank lines, keeping headings attached to the paragraph below them."""
    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return raw_paragraphs

def _last_heading(paragraphs: List[str], upto_index: int) -> Optional[str]:
    """Walk backwards from upto_index to find the most recent markdown heading."""
    for p in reversed(paragraphs[: upto_index + 1]):
        first_line = p.splitlines()[0].strip()
        if first_line.startswith("#"):
            return first_line.lstrip("#").strip()
    return None

def chunk_markdown(
    text: str,
    chunk_size_tokens: int = None,
    overlap_tokens: int = None,
) -> List[Chunk]:
    """
    Chunk markdown text into ~chunk_size_tokens pieces with overlap.

    Strategy: greedily accumulate whole paragraphs until adding the next
    paragraph would exceed chunk_size_tokens, then start a new chunk that
    begins with the last `overlap_tokens` worth of the previous chunk for
    context continuity. Falls back to hard token-splitting for any single
    paragraph that alone exceeds chunk_size_tokens.
    """
    chunk_size_tokens = chunk_size_tokens or settings.chunk_size_tokens
    overlap_tokens = overlap_tokens or settings.chunk_overlap_tokens

    paragraphs = _split_into_paragraphs(text)
    if not paragraphs:
        return []

    chunks: List[Chunk] = []
    current_parts: List[str] = []
    current_tokens = 0
    chunk_index = 0

    def flush():
        nonlocal current_parts, current_tokens, chunk_index
        if not current_parts:
            return
        content = "\n\n".join(current_parts)
        heading = _last_heading(paragraphs, len(paragraphs) - 1)
        chunks.append(
            Chunk(
                content=content,
                chunk_index=chunk_index,
                token_count=current_tokens,
                heading_context=heading,
            )
        )
        chunk_index += 1

    for para in paragraphs:
        para_tokens = len(_ENCODING.encode(para))

        # Split an oversized paragraph
        if para_tokens > chunk_size_tokens:
            flush()
            current_parts, current_tokens = [], 0
            token_ids = _ENCODING.encode(para)
            for start in range(0, len(token_ids), chunk_size_tokens - overlap_tokens):
                piece_ids = token_ids[start : start + chunk_size_tokens]
                piece_text = _ENCODING.decode(piece_ids)
                chunks.append(
                    Chunk(content=piece_text, chunk_index=chunk_index, token_count=len(piece_ids))
                )
                chunk_index += 1
            continue

        if current_tokens + para_tokens > chunk_size_tokens and current_parts:
            flush()

            # Seed chunk from the tail of previous chunk
            prev_text = chunks[-1].content
            prev_ids = _ENCODING.encode(prev_text)
            overlap_ids = prev_ids[-overlap_tokens:] if overlap_tokens else []
            overlap_text = _ENCODING.decode(overlap_ids) if overlap_ids else ""
            current_parts = [overlap_text] if overlap_text else []
            current_tokens = len(overlap_ids)

        current_parts.append(para)
        current_tokens += para_tokens

    flush()
    return chunks