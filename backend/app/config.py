"""Runtime settings, read from environment variables (and an optional .env file).

Secrets (API keys, database passwords) only ever come from the environment.
They are never read from or written to the repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
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
    # Departments created in the app (Admin → Departments), one YAML file each,
    # read together with config/spaces/ (app/spaces.py). Writable, unlike /config.
    spaces_dir: Path = Field(
        default=REPO_ROOT / "deploy" / "data" / "spaces", alias="SOP_SPACES_DIR"
    )

    # Models run locally (Ollama); nothing is sent to a cloud provider.
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # The company's time zone: what "today" means for due dates, deadlines and
    # reports, and when the nightly jobs run (app/clock.py). Timestamps are
    # still stored in UTC.
    time_zone: str = Field(default="Asia/Singapore", alias="SOP_TIMEZONE")

    # Development only: the seeded demo accounts (app/demo.py) sign in without a
    # two-factor code. Refused in any other environment; never affects real users.
    demo_skip_2fa: bool = Field(default=False, alias="SOP_DEMO_SKIP_2FA")

    # Slide pictures (app/vault/slides.py): rendered once per deck version.
    cache_dir: Path = Field(default=REPO_ROOT / "deploy" / "data" / "cache", alias="SOP_CACHE_DIR")
    soffice_path: str | None = Field(default=None, alias="SOFFICE_PATH")

    # Signs tokens and encrypts TOTP secrets. Required outside development.
    secret_key: SecretStr | None = Field(default=None, alias="SOP_SECRET_KEY")
    access_token_minutes: int = Field(default=15, alias="ACCESS_TOKEN_MINUTES")
    refresh_token_days: int = Field(default=14, alias="REFRESH_TOKEN_DAYS")
    invite_hours: int = Field(default=72, alias="INVITE_HOURS")

    @model_validator(mode="after")
    def _demo_skip_2fa_only_in_development(self) -> Settings:
        if self.demo_skip_2fa and self.environment != "development":
            raise ValueError("SOP_DEMO_SKIP_2FA is only allowed with SOP_ENV=development")
        return self

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
