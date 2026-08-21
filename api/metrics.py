from prometheus_client import Counter, Histogram

# --- Latency, broken out by pipeline stage ---
EMBEDDING_LATENCY = Histogram(
    "reposrag_embedding_seconds",
    "Time spent embedding the incoming query",
)

RETRIEVAL_LATENCY = Histogram(
    "reposrag_retrieval_seconds",
    "Time spent on pgvector similarity search",
)

GENERATION_LATENCY = Histogram(
    "reposrag_generation_seconds",
    "Time spent generating an answer via Ollama Qwen 2.5",
)

# --- Retrieval quality proxy ---
TOP1_SIMILARITY = Histogram(
    "reposrag_top1_similarity",
    "Cosine similarity score of the top retrieved chunk per query",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# --- Throughput / errors ---
QUERY_COUNT = Counter(
    "reposrag_queries_total",
    "Total number of /query requests received",
)

QUERY_ERRORS = Counter(
    "reposrag_query_errors_total",
    "Total number of /query requests that errored",
    labelnames=("stage",),
)

OLLAMA_TIMEOUTS = Counter(
    "reposrag_ollama_timeouts_total",
    "Total number of Ollama generation calls that timed out or failed",
)
