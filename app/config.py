from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """Base configuration to determine environment state."""

    ENV_STATE: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class GlobalConfig(BaseSettings):
    """Global configuration with all settings."""

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_DB: str

    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    REDIS_HOST: str
    REDIS_PORT: str

    SUPABASE_URL: str
    SUPABASE_JWT_SECRET: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_STORAGE_BUCKET: str

    CORS_ORIGINS: str

    GITHUB_TOKEN: Optional[str] = None

    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    OLLAMA_TIMEOUT: int
    OLLAMA_MAX_RETRIES: int
    OLLAMA_CONTEXT_SIZE: int

    def _build_database_url(self, driver: str) -> str:
        """Build database URL with proper URL encoding."""
        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql+{driver}://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url(self) -> str:
        """Construct async database URL for asyncpg."""
        return self._build_database_url("asyncpg")

    @property
    def database_url_sync(self) -> str:
        """Construct synchronous database URL for Alembic migrations."""
        return self._build_database_url("psycopg2")

    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"


class DevConfig(GlobalConfig):
    """Development environment configuration."""

    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        env_prefix="DEV_",
        extra="ignore",
    )


class ProdConfig(GlobalConfig):
    """Production environment configuration."""

    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        env_prefix="PROD_",
        extra="ignore",
    )


def get_config(env_state: Optional[str] = None) -> GlobalConfig:
    """
    Factory function to get configuration based on ENV_STATE.

    Args:
        env_state: Environment state ('dev' or 'prod'). If None, reads from BaseConfig.

    Returns:
        DevConfig if env_state='dev', otherwise ProdConfig.
    """
    if env_state is None:
        env_state = BaseConfig().ENV_STATE or "prod"

    configs = {"dev": DevConfig, "prod": ProdConfig}
    return configs.get(env_state.lower(), ProdConfig)()


settings = get_config()
