from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str # Removed hard-coded credential as per Jira Ticket RAG-26

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    embedding_device: str = "auto" # Options are: auto, cpu, cuda, mps

    top_k: int = 5
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()