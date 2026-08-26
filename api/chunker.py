import ast
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

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

def _accumulate_segments(
    segments: List[Tuple[Optional[str], List[str]]],
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> List[Chunk]:
    """
    Accumulate labeled segments into token-budget chunks. Added for
    function/class-aware code chunking as per Jira Ticket RAG-18; reused by
    chunk_markdown's heading-aware sectioning (RAG-21).

    Each segment is (label, parts): `parts` are text blocks (paragraphs, or
    a single code-definition body) belonging to one heading/function/class.
    Parts within a segment are greedily accumulated up to chunk_size_tokens,
    seeding each new chunk with the previous chunk's tail (overlap_tokens)
    for continuity. A segment boundary always flushes and starts a fresh
    chunk with no seeded overlap, since a new heading/function/class is a
    new topic. `label` becomes every resulting chunk's `heading_context`.
    An oversized single part is hard-split on tokens.
    """
    chunks: List[Chunk] = []
    current_parts: List[str] = []
    current_tokens = 0
    current_label: Optional[str] = None
    chunk_index = 0

    def flush():
        nonlocal current_parts, current_tokens, chunk_index
        if not current_parts:
            return
        content = "\n\n".join(current_parts)
        chunks.append(
            Chunk(content=content, chunk_index=chunk_index, token_count=current_tokens, heading_context=current_label)
        )
        chunk_index += 1

    for label, parts in segments:
        flush()
        current_parts, current_tokens = [], 0
        current_label = label

        for part in parts:
            part_tokens = len(_ENCODING.encode(part))

            if part_tokens > chunk_size_tokens:
                flush()
                current_parts, current_tokens = [], 0
                token_ids = _ENCODING.encode(part)
                for start in range(0, len(token_ids), chunk_size_tokens - overlap_tokens):
                    piece_ids = token_ids[start : start + chunk_size_tokens]
                    piece_text = _ENCODING.decode(piece_ids)
                    chunks.append(
                        Chunk(
                            content=piece_text,
                            chunk_index=chunk_index,
                            token_count=len(piece_ids),
                            heading_context=current_label,
                        )
                    )
                    chunk_index += 1
                continue

            if current_tokens + part_tokens > chunk_size_tokens and current_parts:
                flush()
                prev_text = chunks[-1].content
                prev_ids = _ENCODING.encode(prev_text)
                overlap_ids = prev_ids[-overlap_tokens:] if overlap_tokens else []
                overlap_text = _ENCODING.decode(overlap_ids) if overlap_ids else ""
                current_parts = [overlap_text] if overlap_text else []
                current_tokens = len(overlap_ids)

            current_parts.append(part)
            current_tokens += part_tokens

    flush()
    return chunks

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


# --- Code chunking (RAG-18) ---

_JS_TS_DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)"
    r"|^\s*(?:export\s+)?class\s+(\w+)"
    r"|^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(",
    re.MULTILINE,
)
_GO_DEF_RE = re.compile(
    r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)"
    r"|^type\s+(\w+)\s+struct",
    re.MULTILINE,
)

_REGEX_CHUNKERS = {".js": _JS_TS_DEF_RE, ".ts": _JS_TS_DEF_RE, ".go": _GO_DEF_RE}


def _python_segments(text: str) -> List[Tuple[Optional[str], List[str]]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [(None, [text])]

    top_level_defs = [
        n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if not top_level_defs:
        return [(None, [text])]

    segments: List[Tuple[Optional[str], List[str]]] = []
    lines = text.splitlines()
    preamble = "\n".join(lines[: top_level_defs[0].lineno - 1]).strip()
    if preamble:
        segments.append((None, [preamble]))

    for node in top_level_defs:
        source = ast.get_source_segment(text, node)
        if source:
            segments.append((node.name, [source]))

    return segments


def _regex_segments(text: str, pattern: "re.Pattern") -> List[Tuple[Optional[str], List[str]]]:
    matches = list(pattern.finditer(text))
    if not matches:
        return [(None, [text])]

    segments: List[Tuple[Optional[str], List[str]]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        segments.append((None, [preamble]))

    for i, m in enumerate(matches):
        name = next((g for g in m.groups() if g), None)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start() : end].strip()
        if body:
            segments.append((name, [body]))

    return segments


def chunk_code(
    text: str,
    file_ext: str,
    chunk_size_tokens: int = None,
    overlap_tokens: int = None,
) -> List[Chunk]:
    """
    Chunk a source file function/class-aware (RAG-18): each top-level
    function/class becomes its own segment (heading_context = its name), so
    a citation points at a specific definition instead of an arbitrary
    token window. Falls back to a single unlabeled segment — chunked the
    same way an oversized paragraph is — when the file can't be parsed
    (invalid Python) or no top-level definitions are found (unsupported
    language or a file with no functions/classes).
    """
    chunk_size_tokens = chunk_size_tokens or settings.chunk_size_tokens
    overlap_tokens = overlap_tokens or settings.chunk_overlap_tokens

    if not text.strip():
        return []

    if file_ext == ".py":
        segments = _python_segments(text)
    elif file_ext in _REGEX_CHUNKERS:
        segments = _regex_segments(text, _REGEX_CHUNKERS[file_ext])
    else:
        segments = [(None, [text])]

    return _accumulate_segments(segments, chunk_size_tokens, overlap_tokens)