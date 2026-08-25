# ReposRAG

A self-hosted Retrieval-Augmented Generation (RAG) service for asking natural-language
questions over your own repos' documentation. No paid APIs — generation runs on a local
Ollama model, embeddings run on a local sentence-transformers model.

## Architecture

```
 ingest.py
   │  clone/read repo docs (README.md, docs/**/*.md)
   ▼
 chunker.py  ──► fixed-size chunks (~500 tokens, 50 overlap), paragraph-aware
   ▼
 embeddings.py ──► sentence-transformers (all-MiniLM-L6-v2)
   ▼
 Postgres + pgvector  (chunks table: content + metadata + embedding)

 FastAPI /query
   │  1. embed question
   │  2. pgvector cosine similarity search (top-k)
   │  3. assemble prompt with retrieved chunks
   ▼
 Ollama (qwen2.5:3b)  ──► grounded answer + cited sources

 Prometheus  ──► scrapes /metrics (latency by stage, retrieval quality, errors)
 Grafana     ──► dashboards over Prometheus data
```

## Prerequisites

- Docker + Docker Compose
- [Ollama](https://ollama.com) installed on the host with the model pulled:
  ```bash
  ollama pull qwen2.5:3b
  ```

  Ollama must be running (`ollama serve`, or it auto-starts on most installs) and
  reachable at `http://localhost:11434` on the host.

## Setup

```bash
cp .env.example .env
docker-compose up --build
```

This starts:

| Service            | URL                                                      |
| ------------------ | -------------------------------------------------------- |
| API                | http://localhost:8000                                    |
| API docs (Swagger) | http://localhost:8000/docs                               |
| Prometheus         | http://localhost:9090                                    |
| Grafana            | http://localhost:3000 (admin/admin, or anonymous viewer) |

Check health:

```bash
curl http://localhost:8000/health
```

## Ingesting documentation

Run ingestion from your host (needs the same Python deps — see `requirements.txt` —
or `docker-compose exec api ...` to run inside the container):

```bash
# Local path
python -m ingestion.ingest --source local --path ../clockwise --repo-name clockwise

# Or clone directly from GitHub
python -m ingestion.ingest --source git --url https://github.com/you/pickle-rick.git --repo-name pickle-rick
```

Re-running for the same `--repo-name` replaces that repo's chunks (idempotent).

## Managing ingested repos

```bash
# List every ingested repo, with chunk count and last-ingested timestamp
curl http://localhost:8000/repos

# Remove a repo's chunks entirely (without re-ingesting an empty replacement)
curl -X DELETE http://localhost:8000/repos/clockwise
```

## Querying

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I install ClockWise?", "repo": "clockwise"}'
```

Response includes the generated answer, the source chunks used (with similarity
scores), and a timing breakdown per pipeline stage.

### Streaming

`POST /query/stream` takes the same request body and streams the answer as
Server-Sent Events instead of waiting for the full generation to finish:

```bash
curl -N -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I install ClockWise?", "repo": "clockwise"}'
```

Emits a `token` event per generated token, then a single `done` event carrying
`sources` and `timings_seconds` once generation completes.

### Auth and rate limiting

`/query`, `/query/stream`, and both `/repos` routes accept an optional
`X-API-Key` header. Auth is **off by default** (`API_KEY` unset in `.env`) for
local/dev use; once `API_KEY` is set, every guarded route requires a matching
header. All guarded routes are also rate-limited per client IP
(`RATE_LIMIT_PER_MINUTE`, default 60/minute).

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"question": "How do I install ClockWise?", "repo": "clockwise"}'
```

## Evaluation

1. Fill in real `expected_answer` values in `eval/qa_testset.json` (currently
   placeholders — replace with the actual correct answers from your repos).
2. With the stack running and content ingested:
   ```bash
   python -m eval.run_eval --api-url http://localhost:8000
   ```

   This scores faithfulness and answer relevancy via DeepEval, using the local
   Ollama model as the judge (no paid judge API needed), and writes
   `eval/eval_report.csv`.

## Observability

Prometheus scrapes `/metrics` on the API every 5s. Grafana auto-provisions a
"ReposRAG Overview" dashboard with:

- Embedding / retrieval / generation latency (p95), broken out by stage
- Top-1 retrieval similarity distribution (low scores flag corpus gaps)
- Query throughput and error rate by pipeline stage
- Ollama timeout count

## Chunking strategy & trade-offs

Chunks are built by greedily accumulating whole markdown paragraphs up to
~500 tokens, with the last ~50 tokens of a chunk carried into the next chunk
as overlap for context continuity across the boundary. Oversized single
paragraphs are hard-split on tokens. This is simple and cheap, but not
semantically aware — a future iteration could chunk by heading section
instead of raw token count, or use a semantic chunker that groups by topic
similarity.

## Known limitations

- Embedding still defaults to CPU (`EMBEDDING_DEVICE=auto` falls back to CPU
  when no GPU is detected) — fine for a handful of small repos, slow for
  large corpora. GPU is opt-in; see [GPU Acceleration](#gpu-acceleration-optional)
  below.
- Chunking is still fixed-size/paragraph-greedy (see "Chunking strategy &
  trade-offs" above) — heading-aware or semantic chunking remains a future
  iteration, not yet built.
- IVFFlat index is tuned for small datasets (`lists = 100`); revisit for
  larger corpora.
- Retrieval is vector-only — no keyword/hybrid signal or reranking yet.
- The evaluation test set is small (hand-written) and repo-specific — good
  for iteration signal, not a statistically rigorous benchmark.

## GPU Acceleration (optional)

- **Embeddings**: set `EMBEDDING_DEVICE=cuda` (NVIDIA) or `EMBEDDING_DEVICE=mps` (Apple Silicon) in `.env`,
  or leave it on `auto` (default) to detect automatically. Falls back to CPU if no GPU is found.
- **Ollama**: uses the host GPU automatically if one is available and drivers are installed —
  no ReposRAG-side configuration needed. See https://ollama.com for host GPU setup.

## Operations

CI/CD runs on GitHub Actions (Development/QA/Main pipelines), and structured
JSON logging with per-request correlation IDs is available for debugging.
See [docs/runbook.md](docs/runbook.md) for pipeline details, log format, and
GPU setup.

## Optional stretch stages (not included here)

See `ReposRAG-Implementation-Plan.md` for Stage 8 (LangChain/LangGraph
refactor) and Stage 9 (Kubernetes deployment), which build on top of this
codebase.
