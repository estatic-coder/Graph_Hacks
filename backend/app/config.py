from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "ASTERION API"
    environment: str = "development"
    falkordb_url: str = "redis://localhost:6379"
    log_level: str = "info"
    ai_provider: str = "gemini"
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"
    default_model: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

