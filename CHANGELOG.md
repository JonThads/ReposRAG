# Changelog

All notable changes to ReposRAG are documented here, newest first.

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
