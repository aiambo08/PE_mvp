from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "PE Deal Sourcing MVP"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    LLM_PROVIDER: Literal["gemini", "ollama", "openai"] = "ollama"

    GEMINI_API_KEY: str = ""  # Opcional cuando LLM_PROVIDER="ollama"
    GEMINI_MODEL: str = "gemini-2.0-flash"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    LOCAL_LLM_MODEL: str = "qwen2.5:7b-instruct-q5_K_M"
    LLM_NUM_CTX: int = 16_384          # Context window for Ollama (default 2048 causes silent truncation)
    LLM_SEED: int = 42                 # Deterministic seed for reproducible LLM outputs
    CACHE_TTL_HOURS: float = 24.0      # Hours before a cached company analysis is considered stale

    SCRAPER_HEADLESS: bool = True
    SCRAPER_TIMEOUT: int = 30_000
    MAX_CONCURRENT_SCRAPES: int = 5
    MAX_CONTEXT_CHARS: int = 15_000  

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
