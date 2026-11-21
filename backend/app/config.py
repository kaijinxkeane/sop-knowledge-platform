"""Runtime settings, read from environment variables (and an optional .env file).

Secrets (API keys, database passwords) only ever come from the environment.
They are never read from or written to the repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", alias="SOP_ENV")

    database_url: str = Field(
        default="postgresql+asyncpg://sop:sop-dev-only@localhost:5433/sop", alias="DATABASE_URL"
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Where the vault (Obsidian-format git repo) is mounted, and where config lives.
    vault_path: Path = Field(default=REPO_ROOT / "deploy" / "data" / "vault", alias="VAULT_PATH")
    config_dir: Path = Field(default=REPO_ROOT / "config", alias="SOP_CONFIG_DIR")

    # Model providers. The Anthropic key is optional so the stack can run fully
    # local; tiers that need it fail closed with a clear error.
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    # Expected Anthropic organisation for production; a mismatch is reported at startup.
    anthropic_expected_org: str | None = Field(default=None, alias="ANTHROPIC_EXPECTED_ORG")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Signs tokens and encrypts TOTP secrets. Required outside development.
    secret_key: SecretStr | None = Field(default=None, alias="SOP_SECRET_KEY")
    access_token_minutes: int = Field(default=15, alias="ACCESS_TOKEN_MINUTES")
    refresh_token_days: int = Field(default=14, alias="REFRESH_TOKEN_DAYS")
    invite_hours: int = Field(default=72, alias="INVITE_HOURS")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        # Plain http is only acceptable on a developer's own machine.
        return self.environment != "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
