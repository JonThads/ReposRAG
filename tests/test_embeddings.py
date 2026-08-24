import sys
import types
from unittest.mock import MagicMock

import numpy as np

from api import embeddings


def test_resolve_device_passes_through_explicit_choices():
    assert embeddings.resolve_device("cpu") == "cpu"
    assert embeddings.resolve_device("cuda") == "cuda"


def test_resolve_device_auto_falls_back_to_cpu_without_torch(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    assert embeddings.resolve_device("auto") == "cpu"


def test_resolve_device_auto_prefers_cuda_when_available(monkeypatch):
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: True),
        backends=types.SimpleNamespace(mps=None),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert embeddings.resolve_device("auto") == "cuda"


def test_resolve_device_auto_prefers_mps_when_cuda_unavailable(monkeypatch):
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: True)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert embeddings.resolve_device("auto") == "mps"


def test_resolve_device_auto_falls_back_to_cpu_when_nothing_available(monkeypatch):
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        backends=types.SimpleNamespace(mps=None),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert embeddings.resolve_device("auto") == "cpu"


def test_embed_text_normalizes_and_returns_float32(monkeypatch):
    fake_model = MagicMock()
    fake_model.encode.return_value = np.array([0.1, 0.2, 0.3])
    monkeypatch.setattr(embeddings, "get_embedder", lambda: fake_model)

    result = embeddings.embed_text("hello")

    fake_model.encode.assert_called_once_with("hello", normalize_embeddings=True)
    assert result.dtype == np.float32
    assert result.shape == (3,)


def test_embed_batch_shows_progress_bar_above_threshold(monkeypatch):
    fake_model = MagicMock()
    fake_model.encode.return_value = np.zeros((25, 3))
    monkeypatch.setattr(embeddings, "get_embedder", lambda: fake_model)

    embeddings.embed_batch([f"text {i}" for i in range(25)])

    _, kwargs = fake_model.encode.call_args
    assert kwargs["show_progress_bar"] is True


def test_embed_batch_hides_progress_bar_at_or_below_threshold(monkeypatch):
    fake_model = MagicMock()
    fake_model.encode.return_value = np.zeros((5, 3))
    monkeypatch.setattr(embeddings, "get_embedder", lambda: fake_model)

    embeddings.embed_batch([f"text {i}" for i in range(5)])

    _, kwargs = fake_model.encode.call_args
    assert kwargs["show_progress_bar"] is False
