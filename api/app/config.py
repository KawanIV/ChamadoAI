from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://chamados:chamados@db:5432/chamados"
    jwt_secret: str = Field(min_length=32)
    public_link_secret: str = Field(min_length=32)
    cors_origins: str = "http://localhost:3000"
    ollama_url: str = "http://ollama:11434"
    default_model: str = "ternary-bonsai:8b"
    environment: str = "production"
    cookie_secure: bool = False

@lru_cache
def get_settings() -> Settings:
    return Settings()
