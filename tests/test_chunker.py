import tiktoken

from api.chunker import chunk_markdown

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _token_count(text: str) -> int:
    return len(_ENCODING.encode(text))


def test_empty_input_returns_no_chunks():
    assert chunk_markdown("", chunk_size_tokens=50, overlap_tokens=10) == []


def test_whitespace_only_input_returns_no_chunks():
    assert chunk_markdown("   \n\n   ", chunk_size_tokens=50, overlap_tokens=10) == []


def test_single_paragraph_under_budget_is_one_chunk():
    chunks = chunk_markdown("Hello world.", chunk_size_tokens=50, overlap_tokens=10)
    assert len(chunks) == 1
    assert chunks[0].content == "Hello world."
    assert chunks[0].chunk_index == 0


def test_paragraphs_that_fit_together_are_not_split():
    text = "First paragraph.\n\nSecond paragraph."
    chunks = chunk_markdown(text, chunk_size_tokens=1000, overlap_tokens=10)
    assert len(chunks) == 1
    assert chunks[0].content == text


def test_paragraph_boundaries_preserved_when_budget_forces_a_split():
    para_a = "Alpha bravo charlie delta."
    para_b = "Echo foxtrot golf hotel."
    text = f"{para_a}\n\n{para_b}"

    # Exactly fits one paragraph, forcing a flush before the next is added.
    # Note: chunk_markdown treats overlap_tokens=0 as falsy and silently
    # falls back to the configured default (an `or`-default quirk in
    # chunker.py, out of scope here) — use 1 to keep the seed negligible.
    budget = _token_count(para_a)
    chunks = chunk_markdown(text, chunk_size_tokens=budget, overlap_tokens=1)

    assert len(chunks) == 2
    assert chunks[0].content == para_a
    assert chunks[0].chunk_index == 0
    assert chunks[1].content.endswith(para_b)
    assert chunks[1].chunk_index == 1


def test_oversized_single_paragraph_is_hard_split_within_budget():
    long_paragraph = " ".join(f"word{i}" for i in range(200))
    budget = 20

    chunks = chunk_markdown(long_paragraph, chunk_size_tokens=budget, overlap_tokens=5)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= budget
    assert "word0" in chunks[0].content


def test_overlap_seeds_the_next_chunk_with_the_previous_tail():
    paragraphs = [f"Paragraph{i} has several distinct words in it." for i in range(6)]
    text = "\n\n".join(paragraphs)

    # Tight enough that each paragraph forces a new chunk.
    budget = _token_count(paragraphs[0]) + 2
    overlap = 5

    chunks = chunk_markdown(text, chunk_size_tokens=budget, overlap_tokens=overlap)

    assert len(chunks) > 1
    tail_ids = _ENCODING.encode(chunks[0].content)[-overlap:]
    tail_of_first = _ENCODING.decode(tail_ids)
    assert chunks[1].content.startswith(tail_of_first)


def test_chunk_indices_are_sequential():
    text = "\n\n".join(f"Paragraph {i}." for i in range(5))
    chunks = chunk_markdown(text, chunk_size_tokens=1000, overlap_tokens=10)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
