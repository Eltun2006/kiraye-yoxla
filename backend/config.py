from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "anthropic"  # "anthropic" | "gemini"

    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Law retrieval embeddings: "gemini" (API, light) | "local" (multilingual-e5-base, needs requirements-dev.txt)
    embed_provider: str = "gemini"
    gemini_embed_model: str = "gemini-embedding-001"

    database_url: str = "sqlite:///./kiraye.db"
    max_upload_mb: int = 5
    max_chars: int = 40_000
    max_clauses: int = 100

    # Abuse protection (each analysis is one LLM call; the Gemini free tier allows only ~20 per day)
    rate_limit_per_hour: int = 5        # new analyses per client IP per hour
    daily_analysis_limit: int = 15      # all clients together, per UTC day — protects the LLM quota/budget
    trust_proxy: bool = False           # behind a reverse proxy (e.g. Hugging Face Spaces) use X-Forwarded-For
    retention_days: int = 30            # analyses (contracts may contain personal data) are deleted after this

    # Deployment: fill an empty law table from data/law on startup (Docker sets this; tests must not)
    auto_ingest_law: bool = False


settings = Settings()
