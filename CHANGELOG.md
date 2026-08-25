# Changelog

All notable changes to ReposRAG are documented here, newest first.

## 2026-08-24

### Added
- `GET /repos` endpoint listing every ingested repo with its chunk count and last-ingested timestamp. ([RAG-14](https://pickle-rick.atlassian.net/browse/RAG-14))
- `DELETE /repos/{repo_name}` endpoint to remove a repo's chunks without re-ingesting an empty replacement. ([RAG-15](https://pickle-rick.atlassian.net/browse/RAG-15))
- `POST /query/stream` — a Server-Sent Events streaming mode for `/query`, emitting `token` events as the answer is generated and a final `done` event carrying sources and timings, backed by a new `stream_answer()` in [api/generation.py](api/generation.py). ([RAG-16](https://pickle-rick.atlassian.net/browse/RAG-16))
- Retry/backoff around transient Ollama failures (`httpx.TimeoutException`/`ConnectError`/`RemoteProtocolError`) in [api/generation.py](api/generation.py), configurable via `OLLAMA_MAX_RETRIES`/`OLLAMA_RETRY_BACKOFF_SECONDS`. ([RAG-8](https://pickle-rick.atlassian.net/browse/RAG-8))
- Explicit 404 with the list of known repos when `/query`'s `repo` filter doesn't match any ingested repo, distinguishing a typo'd repo from a genuinely empty index. ([RAG-9](https://pickle-rick.atlassian.net/browse/RAG-9))
- A `pytest` unit suite (`tests/`) covering `chunker.py`, `embeddings.py`, the Ollama retry logic, and repo-filter validation — mocked so it needs no live Postgres/Ollama; dev-only deps split into `requirements-dev.txt`. ([RAG-10](https://pickle-rick.atlassian.net/browse/RAG-10))
- Opt-in `X-API-Key` auth and per-IP rate limiting (`slowapi`) on `/query`, `/query/stream`, and both `/repos` routes — auth is off by default (`API_KEY` unset) for local/dev use; rate limit configurable via `RATE_LIMIT_PER_MINUTE`. ([RAG-17](https://pickle-rick.atlassian.net/browse/RAG-17))

### Changed
- Extracted `/query`'s embed-and-retrieve logic into a shared `_retrieve()` helper in [api/main.py](api/main.py) so `/query` and `/query/stream` don't duplicate it; non-streaming `/query` behavior is unchanged. ([RAG-16](https://pickle-rick.atlassian.net/browse/RAG-16))

### Fixed
- N/A

## 2026-08-23

### Added
- GPU device selection for the embedding model — `EMBEDDING_DEVICE` setting (`auto`/`cpu`/`cuda`/`mps`) in [api/embeddings.py](api/embeddings.py), auto-detected via `torch` at model load time and falling back to CPU when no GPU is available. ([RAG-24](https://pickle-rick.atlassian.net/browse/RAG-24))
- Structured JSON logging (`api/logging_config.py`) across the API and ingestion CLI, with a per-request correlation ID (`x-request-id`) threaded through the embedding/retrieval/generation stages of `/query`. ([RAG-25](https://pickle-rick.atlassian.net/browse/RAG-25))

### Changed
- `DATABASE_URL` no longer has a hardcoded default in [api/config.py](api/config.py) — the API now fails fast at boot with a clear error if it isn't set, instead of silently falling back to a dev credential. ([RAG-26](https://pickle-rick.atlassian.net/browse/RAG-26))
- `docker-compose.yml` no longer hardcodes the Postgres password in two places (the `db` service and the `api` service's `DATABASE_URL`, which previously silently overrode `.env`); both now derive from `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`, with Compose itself failing fast if `POSTGRES_PASSWORD` is unset. ([RAG-26](https://pickle-rick.atlassian.net/browse/RAG-26))
- `.env.example` credential values replaced with explicit `CHANGE_ME` placeholders instead of a real-looking default password. ([RAG-26](https://pickle-rick.atlassian.net/browse/RAG-26))

### Fixed
- N/A
