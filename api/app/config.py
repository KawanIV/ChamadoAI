from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # DATABASE_URL remains available for development/tests. In Docker, the
    # fields below are preferred so reserved characters in the password are
    # never mistaken for URL separators (for example @, :, / or #).
    database_url: str | None = None
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "chamados"
    db_user: str = "chamados"
    db_password: SecretStr | None = None
    jwt_secret: str = Field(min_length=32)
    public_link_secret: str = Field(min_length=32)
    cors_origins: str = "http://localhost:3000"
    ollama_url: str = "http://ollama:11434"
    default_model: str = "ternary-bonsai:8b"
    environment: str = "production"
    cookie_secure: bool = False

    def sqlalchemy_database_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        if self.db_password is None:
            raise ValueError("DB_PASSWORD deve ser definido quando DATABASE_URL não for usado")
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

@lru_cache
def get_settings() -> Settings:
    return Settings()
