from api.chunker import chunk_code


def test_python_function_becomes_its_own_labeled_chunk():
    source = (
        "import os\n\n"
        "def add(a, b):\n"
        "    return a + b\n\n\n"
        "def subtract(a, b):\n"
        "    return a - b\n"
    )
    chunks = chunk_code(source, ".py", chunk_size_tokens=200, overlap_tokens=10)

    labels = [c.heading_context for c in chunks]
    assert "add" in labels
    assert "subtract" in labels
    add_chunk = next(c for c in chunks if c.heading_context == "add")
    assert "return a + b" in add_chunk.content


def test_python_class_becomes_its_own_labeled_chunk():
    source = "class Greeter:\n    def hello(self):\n        return 'hi'\n"
    chunks = chunk_code(source, ".py", chunk_size_tokens=200, overlap_tokens=10)

    assert any(c.heading_context == "Greeter" for c in chunks)


def test_python_preamble_before_first_def_is_unlabeled():
    source = "import os\nimport sys\n\ndef f():\n    pass\n"
    chunks = chunk_code(source, ".py", chunk_size_tokens=200, overlap_tokens=10)

    assert chunks[0].heading_context is None
    assert "import os" in chunks[0].content


def test_python_syntax_error_falls_back_to_single_unlabeled_chunk():
    chunks = chunk_code("def broken(:\n", ".py", chunk_size_tokens=200, overlap_tokens=10)

    assert len(chunks) == 1
    assert chunks[0].heading_context is None


def test_python_file_with_no_top_level_defs_falls_back_to_single_chunk():
    chunks = chunk_code("x = 1\ny = 2\n", ".py", chunk_size_tokens=200, overlap_tokens=10)

    assert len(chunks) == 1
    assert chunks[0].heading_context is None


def test_js_function_and_class_are_labeled():
    source = (
        "function add(a, b) {\n  return a + b;\n}\n\n"
        "class Widget {\n  render() {}\n}\n"
    )
    chunks = chunk_code(source, ".js", chunk_size_tokens=200, overlap_tokens=10)

    labels = [c.heading_context for c in chunks]
    assert "add" in labels
    assert "Widget" in labels


def test_go_func_is_labeled():
    source = "func Add(a int, b int) int {\n\treturn a + b\n}\n"
    chunks = chunk_code(source, ".go", chunk_size_tokens=200, overlap_tokens=10)

    assert chunks[0].heading_context == "Add"


def test_unsupported_extension_falls_back_to_single_unlabeled_chunk():
    chunks = chunk_code("puts 'hi'\n", ".rb", chunk_size_tokens=200, overlap_tokens=10)

    assert len(chunks) == 1
    assert chunks[0].heading_context is None


def test_empty_source_returns_no_chunks():
    assert chunk_code("", ".py", chunk_size_tokens=200, overlap_tokens=10) == []


def test_oversized_function_is_hard_split_within_budget():
    body_lines = "\n".join(f"    x{i} = {i}" for i in range(300))
    source = f"def big():\n{body_lines}\n"
    chunks = chunk_code(source, ".py", chunk_size_tokens=20, overlap_tokens=5)

    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= 20
        assert c.heading_context == "big"
