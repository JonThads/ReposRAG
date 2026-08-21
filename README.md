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
| Service | URL |
|---|---|
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin, or anonymous viewer) |

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

## Querying

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I install ClockWise?", "repo": "clockwise"}'
```

Response includes the generated answer, the source chunks used (with similarity
scores), and a timing breakdown per pipeline stage.

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

- Embedding runs on CPU by default — fine for a handful of small repos, slow
  for large corpora.
- IVFFlat index is tuned for small datasets (`lists = 100`); revisit for
  larger corpora.
- The evaluation test set is small (hand-written) and repo-specific — good
  for iteration signal, not a statistically rigorous benchmark.

## Optional stretch stages (not included here)

See `ReposRAG-Implementation-Plan.md` for Stage 8 (LangChain/LangGraph
refactor) and Stage 9 (Kubernetes deployment), which build on top of this
codebase.
