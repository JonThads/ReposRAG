# Changelog

All notable changes to ReposRAG are documented here, newest first.

## 2026-08-24

### Added
- `GET /repos` endpoint listing every ingested repo with its chunk count and last-ingested timestamp. ([RAG-14](https://pickle-rick.atlassian.net/browse/RAG-14))
- `DELETE /repos/{repo_name}` endpoint to remove a repo's chunks without re-ingesting an empty replacement. ([RAG-15](https://pickle-rick.atlassian.net/browse/RAG-15))
- `POST /query/stream` — a Server-Sent Events streaming mode for `/query`, emitting `token` events as the answer is generated and a final `done` event carrying sources and timings, backed by a new `stream_answer()` in [api/generation.py](api/generation.py). ([RAG-16](https://pickle-rick.atlassian.net/browse/RAG-16))

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
