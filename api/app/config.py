from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Signalist API"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/signalist"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str | None = None
    openai_report_model: str = "gpt-5.6-sol"
    openai_news_model: str = "gpt-5.6-terra"
    market_data_provider: str = "mock"
    news_user_agent: str = "SignalistResearchBot/0.1 (contact: admin@example.com)"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SIGNALIST_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
