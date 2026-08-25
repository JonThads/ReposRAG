# ReposRAG — Operations Runbook

Operational notes for running and debugging ReposRAG day to day. First-time
setup lives in `README.md`; this is for after it's running.

## GPU acceleration

- **Embeddings**: controlled by `EMBEDDING_DEVICE` in `.env` — `auto`
  (default) detects CUDA/MPS and falls back to CPU if neither is present;
  set explicitly to `cpu`, `cuda`, or `mps` to override detection.
- **Ollama**: uses the host GPU automatically when available; no
  ReposRAG-side configuration. See [ollama.com](https://ollama.com) for host
  GPU driver setup.
- To confirm which device the embedding model actually loaded onto, check
  the structured logs (below) for the `embeddings` logger at startup.

## Structured logging

The API and ingestion CLI emit one JSON object per line to stdout
(`api/logging_config.py`), controlled by `LOG_LEVEL` (default `INFO`):

```json
{"timestamp": "...", "level": "INFO", "logger": "reposrag.api", "message": "query.complete", "request_id": "a1b2c3d4-...", "repo": "clockwise", "embedding_seconds": 0.012, "retrieval_seconds": 0.034, "generation_seconds": 1.21, "top1_similarity": 0.82}
```

- **Correlation ID**: every `/query` and `/query/stream` request gets a
  `request_id` (reused from an incoming `x-request-id` header if present,
  otherwise a generated UUID), threaded through the embedding, retrieval,
  and generation stages and echoed back in the `x-request-id` response
  header. To trace one request end to end: `docker compose logs api | grep
  <request_id>`.
- Key log events: `query.start`, `query.complete`, `query.unknown_repo`,
  `query.no_results`, `query.embedding_failed`, `query.retrieval_failed`,
  `query.generation_failed`/`query.generation_timeout`, `ollama.retry`,
  `repos.list`, `repos.delete`, `repos.delete_unknown`, `auth.rejected`.

## CI/CD pipelines

Three GitHub Actions workflows, gating merges per the branch flow in
`docs/claude-instructions.md`:

| Pipeline | File | Fires on | Checks |
|---|---|---|---|
| Development | `.github/workflows/development.yml` | push to `feature/**`, `fix/**`, `test/**`, `chore/**`, `docs/**`, `refactor/**`, `ci/**` | `ruff` lint, compile check, Docker image build, boot check against `/health` |
| QA | `.github/workflows/qa.yml` | PR/push into `qa` | `pytest` suite, then a live end-to-end smoke test (self-ingests this repo's own docs, then a real `/query` call) against the docker-compose stack |
| Main | `.github/workflows/main.yml` | PR/push into `main` | The QA pipeline, plus a Docker image build check and a `gitleaks` secrets scan |

**Re-running a pipeline**: re-push to the branch, or re-run the failed job
from the GitHub Actions UI (Actions tab → the run → "Re-run jobs").

**Publishing a release image**: not automatic on every `main` merge. Trigger
the Main workflow manually (`workflow_dispatch`) with a `release_tag` input
(e.g. `v1.1.0`) to build, verify, and push `ghcr.io/<repo>:<tag>` and
`:latest`. Leaving `release_tag` blank on a manual run only builds and
verifies — nothing is published.

**Debugging a QA pipeline failure**: the live-smoke job installs and starts
Ollama directly on the runner (not in Docker) and reconfigures the
systemd-managed service to bind `0.0.0.0` so the `api` container can reach it
via `host.docker.internal` — if this job fails at the Ollama install/start
step, check the runner logs for that reconfiguration rather than assuming
the model pull itself failed.
