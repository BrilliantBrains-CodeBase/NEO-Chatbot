from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables or backend/.env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "staging", "production"] = "local"

    # Cloud Supabase Postgres through the Supavisor pooler (transaction mode). Required.
    database_url: str = ""
    supabase_url: str = ""
    # Empty = Redis off (Phase 2). Sessions, slot holds and rate limits then use Postgres and memory.
    redis_url: str = ""

    # Comma separated, so it reads naturally in .env.
    allowed_origins: str = ""

    groq_api_key: str = ""
    gemini_api_key: str = ""
    interakt_api_key: str = ""
    # Cal.com books online consults (Google Meet link) when staff approve them in the CRM.
    calcom_api_key: str = ""
    calcom_event_type_id: int = 0
    # Shared with the Apps Script in each clinic's Google Sheet of Meta leads (/v1/integrations/sheet-leads).
    sheet_webhook_secret: str = ""

    embed_model: str = "BAAI/bge-small-en-v1.5"
    # Where the model files are kept (about 130 MB). Empty: backend/.models. Not a temp folder, which the
    # system may clear and force a new download.
    embed_cache_dir: str = ""

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.groq_api_key or self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
