from typing import Optional

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str # Removed hard-coded credential as per Jira Ticket RAG-26

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_max_retries: int = 2  # Added for retry/backoff as per Jira Ticket RAG-8
    ollama_retry_backoff_seconds: float = 0.5  # base delay; doubles per retry

    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    embedding_device: str = "auto" # Options are: auto, cpu, cuda, mps

    top_k: int = 5
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    log_level: str = "INFO"

    # Added for auth/rate limiting as per Jira Ticket RAG-17.
    # api_key unset (None) disables auth entirely — opt-in for local/dev use.
    api_key: Optional[str] = None
    rate_limit_per_minute: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()