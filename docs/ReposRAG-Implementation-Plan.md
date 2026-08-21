# ReposRAG — Implementation Plan

## Overall Summary

ReposRAG is a fully self-hosted Retrieval-Augmented Generation (RAG) service that lets you ask natural-language questions over your own GitHub repositories' documentation (READMEs, docs folders, etc.). It ingests source docs, chunks and embeds them, stores the vectors in Postgres (pgvector), and answers queries by retrieving relevant chunks and passing them to a locally-running Qwen 2.5 (3B) model via Ollama.

The project has zero recurring API cost — no OpenAI or Anthropic API keys required — and is built entirely on tooling already in use across other projects (FastAPI, Docker, PostgreSQL, GitHub Actions, DeepEval). The goal is both a working demo and a portfolio piece that demonstrates understanding of the full RAG lifecycle: ingestion, chunking strategy, retrieval quality, generation grounding, and evaluation.

**Corpus for v1:** ClockWise, Pickle-Rick, and Tokenomics MCP repo docs (chosen because their content is already well understood, making manual evaluation of answer quality straightforward).

**Scope:** Stages 1–7 form the implemented core of this project — the RAG pipeline itself plus observability, since monitoring retrieval/generation behavior is treated as part of understanding RAG mechanics, not an add-on. All code for Stages 1–7 exists in the `reposrag/` repo. Stages 8–9 (LangChain/LangGraph refactor, Kubernetes deployment) are optional stretch extensions into adjacent skill areas, not yet built, and can be tackled independently after the core is working.

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| API framework | FastAPI | Matches existing stack (Tokenomics MCP, Pickle-Rick) |
| LLM (generation) | Ollama — Qwen 2.5 (3B) | Already running locally; zero cost |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Free, local, CPU-friendly |
| Vector store | PostgreSQL + pgvector | Reuses existing Postgres experience |
| Containerization | Docker / Docker Compose | Matches existing repo pattern |
| CI | GitHub Actions | Matches existing repo pattern |
| Evaluation | DeepEval | Judged by local Ollama model — no paid judge |
| Chunking utility | `tiktoken` or word-count splitter | Simple, swappable later |
| Optional frontend | Streamlit or static HTML | For live demo only |
| Observability (Stage 7) | Prometheus + Grafana | Implemented |
| *Optional (Stage 8)* | LangChain / LangGraph | Framework comparison refactor — not yet built |
| *Optional (Stage 9)* | Kubernetes (kind/minikube) | Deployment/orchestration practice — not yet built |

---

## Stage 1 — Setup & Scaffolding

**Goal:** A running skeleton with health checks, before any RAG logic exists.

- Create repo `reposrag` with standard layout: `/api`, `/ingestion`, `/eval`, `/docker`, `/tests`
- `docker-compose.yml` defining:
  - `api` — FastAPI app container
  - `db` — Postgres with pgvector extension enabled
  - Ollama referenced as an external service (host machine) — not containerized, since it's already running locally
- `.env.example` covering: `DATABASE_URL`, `OLLAMA_HOST`, `OLLAMA_MODEL=qwen2.5:3b`, `EMBEDDING_MODEL=all-MiniLM-L6-v2`, `TOP_K`
- FastAPI skeleton app with a `/health` endpoint that checks DB connectivity and Ollama reachability
- `requirements.txt` / `pyproject.toml` pinned versions
- Initialize git, `.gitignore`, base README stub
- **Definition of done:** `docker-compose up` boots API + DB, `/health` returns 200 with both services reachable

## Stage 2 — Ingestion & Chunking Pipeline

**Goal:** Turn raw repo docs into structured, stored chunks with metadata.

- Ingestion script (`ingest.py`) supports two source modes:
  - Local path (repos already cloned on disk)
  - Remote (`git clone` a repo URL into a temp dir, extract docs, clean up)
- Target files: `README.md`, `/docs/**/*.md`, optionally `CONTRIBUTING.md`
- Chunking strategy:
  - Fixed-size chunks (~500 tokens) with ~50-token overlap to preserve context across boundaries
  - Split on paragraph/heading boundaries where possible before falling back to hard token cuts
- Metadata captured per chunk: source repo name, file path, chunk index, heading context (if available), token count
- Store raw chunk text + metadata in a `chunks` table in Postgres (pre-embedding)
- Idempotency: re-running ingestion for a repo should replace, not duplicate, its chunks
- **Definition of done:** running `python ingest.py --repo clockwise` populates the `chunks` table with correct metadata, verified via a row count + spot-check query

## Stage 3 — Embedding & Vector Storage

**Goal:** Make chunks semantically searchable.

- Load `all-MiniLM-L6-v2` via `sentence-transformers` (downloaded once, cached locally — no internet needed after first run)
- Batch-embed all chunks from Stage 2; store vectors in a `vector` column (pgvector) alongside the `chunks` table (or a linked `embeddings` table)
- Create a similarity index (IVFFlat or HNSW) on the vector column for fast nearest-neighbor search
- CLI command `python ingest.py --embed` (or combined with Stage 2's command) to (re)build the full index from scratch
- Sanity-check script: run a known query, confirm the top result is the expected chunk
- **Definition of done:** a test query against the DB returns semantically relevant chunks ranked correctly by cosine similarity

## Stage 4 — Retrieval + Generation API

**Goal:** The core user-facing RAG endpoint.

- `POST /query` endpoint accepting `{ "question": "...", "repo": "optional filter" }`
- Pipeline: embed the question → pgvector similarity search (top-k, default k=5) → optionally filter by repo → assemble retrieved chunks into a prompt template
- Prompt template includes:
  - System instruction: "Answer only using the provided context. If the answer isn't in the context, say so."
  - Retrieved chunks with source attribution
  - The user's question
- Call Ollama's local REST API (`/api/generate` or `/api/chat`) with `qwen2.5:3b`
- Response includes: generated answer + list of source chunks used (repo, file, chunk index) for traceability
- Basic guardrails: reject empty queries, cap max question length, timeout handling for Ollama calls
- **Definition of done:** querying `/query` with a question about ClockWise returns a grounded answer citing the correct source file

## Stage 5 — Evaluation

**Goal:** Move from "it seems to work" to measured retrieval and answer quality.

- Build a small hand-written Q&A test set (15–30 pairs) from the three source repos — questions you already know the correct answer to
- Integrate DeepEval with metrics:
  - **Faithfulness** — does the answer stay grounded in retrieved context?
  - **Answer relevance** — does the answer address the question?
  - **Contextual precision/recall** — are the right chunks being retrieved?
- Configure DeepEval's judge LLM to use the local Ollama model (avoids any paid judge dependency)
- Run eval as a script (`python eval/run_eval.py`) producing a scored report (CSV or console table)
- Use results to iterate: adjust chunk size/overlap, top-k, or prompt template; re-run eval to confirm improvement
- **Definition of done:** an eval report exists with baseline scores, plus at least one documented iteration that improved a metric

## Stage 6 — Shipping

**Goal:** A polished, reproducible, portfolio-ready deliverable.

- Finalize `docker-compose.yml` so `docker-compose up` runs the full stack end-to-end (assuming Ollama is running on host)
- GitHub Actions workflow: lint (ruff/flake8), run unit tests, optionally run a smoke test against a small fixture DB — matching CI patterns used in ClockWise/Pickle-Rick/Tokenomics MCP
- Write full README:
  - Architecture diagram (ingestion → embedding → retrieval → generation)
  - Chunking strategy rationale and trade-offs considered
  - Evaluation results summary with before/after iteration
  - Setup instructions (prerequisites: Ollama installed + model pulled, Docker)
  - Known limitations (e.g., CPU-only embedding speed, small eval set size)
- Tag a `v1.0` release
- Optional stretch goals (documented as "future work" in README):
  - Simple Streamlit or static HTML frontend hitting `/query` for live demo
  - Hybrid search (keyword + vector)
  - Reranking step before generation
  - Support for additional repos beyond the initial three
- **Definition of done:** a fresh clone of the repo, following only the README, results in a working local demo

---

## Stage 7 — Observability (Prometheus + Grafana) — Implemented

**Goal:** Make retrieval and generation behavior measurable, not just "it seems to work."

- Instrument the FastAPI app using `prometheus-fastapi-instrumentator` (or manual `prometheus_client` counters/histograms) to expose a `/metrics` endpoint
- Add `prometheus` and `grafana` containers to `docker-compose.yml`; configure Prometheus to scrape the FastAPI `/metrics` endpoint on an interval
- Key metrics to capture:
  - **Latency breakdown** — embedding time, pgvector search time, Ollama generation time, tracked as separate histograms so bottlenecks are visible
  - **Retrieval quality proxy** — top-k similarity scores per query (consistently low scores signal a question outside the corpus's coverage)
  - **Throughput/errors** — requests/sec, error rate, Ollama timeout/failure count
  - **Resource split** — proportion of total request time spent in embedding vs. generation
- Build a Grafana dashboard with panels for the above, backed by the Prometheus data source
- **Definition of done:** running the full stack and issuing several `/query` requests produces visible, correctly-labeled metrics in a Grafana dashboard, with latency broken out by pipeline stage

## Stage 8 — LangChain / LangGraph Refactor (Optional — Not Yet Built)

**Goal:** Rebuild the same pipeline using LangChain/LangGraph to compare hand-rolled vs. framework-based RAG, after already understanding the mechanics manually.

- Swap the custom chunker for LangChain's `RecursiveCharacterTextSplitter`
- Swap manual `sentence-transformers` + raw pgvector queries for LangChain's `PGVector` vector store integration
- Rebuild the `/query` pipeline using a `RetrievalQA` chain (or LCEL equivalent) instead of manual prompt assembly
- If exploring multi-step behavior (e.g., query rewriting, multi-hop retrieval, self-correction loops), model that flow as a LangGraph graph rather than a single linear chain
- Compare against the Stage 1–6 implementation: same eval set (Stage 5), same metrics — does the framework version score differently, and why?
- **Definition of done:** a parallel implementation (e.g. `/api-langchain`) passes the same DeepEval test set, with a written comparison of results and trade-offs against the hand-rolled version

## Stage 9 — Kubernetes Deployment (Optional — Not Yet Built)

**Goal:** Practice deployment/orchestration skills using this project as the workload, separate from the RAG-learning objective itself.

- Write Kubernetes manifests (or a Helm chart) for the `api` and `db` services
- Use a `ConfigMap` for non-secret env vars and a `Secret` for anything sensitive (DB credentials)
- Use a `PersistentVolumeClaim` for Postgres data so it survives pod restarts
- Keep Ollama running on the host (outside the cluster) and reach it from within the cluster via an `ExternalName` Service or equivalent host-networking approach, since self-hosting the LLM itself on K8s (GPU scheduling, model caching) is a separate, larger topic
- Run locally via `kind` or `minikube` to keep this at zero cost — no cloud cluster needed
- **Definition of done:** `kubectl apply -f k8s/` brings up a working `api` + `db` deployment on a local cluster, reachable via a `kubectl port-forward` or local Ingress, with the same `/query` behavior as the Docker Compose version
