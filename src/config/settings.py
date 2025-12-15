"""Environment configuration and validation.

This module defines strongly-typed application settings loaded from environment variables
(optionally via a local `.env` file).

It enforces critical invariants required by the project specification, such as locking the DB
session timezone to UTC for deterministic date boundaries.
"""

from __future__ import annotations

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    The settings are validated to keep runtime behavior deterministic and aligned with the project
    specification (for example, DB session timezone must be UTC).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    db_timezone: str = Field(default="UTC", alias="DB_TIMEZONE")

    llm_enabled: bool = Field(default=False, alias="LLM_ENABLED")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")

    @field_validator("db_timezone")
    @classmethod
    def validate_db_timezone_is_utc(cls, value: str) -> str:
        """Validate that the DB timezone is locked to UTC.

        The project interprets user dates as UTC calendar days and requires deterministic timestamp
        comparisons. Any other timezone is rejected at startup.
        """

        if value.upper() != "UTC":
            raise ValueError("DB_TIMEZONE must be UTC")
        return "UTC"

    @model_validator(mode="after")
    def validate_llm_config(self) -> Settings:
        """Validate the optional LLM parser configuration.

        If LLM intent parsing is enabled, an API key must be provided.
        """

        if self.llm_enabled and not self.llm_api_key:
            raise ValueError("LLM_API_KEY is required when LLM_ENABLED=true")
        return self


def load_settings() -> Settings:
    """Load and validate settings from environment variables.

    Raises:
        RuntimeError: If the environment configuration is missing or invalid.
    """

    try:
        return Settings()
    except ValidationError as exc:
        # Raising here is fine: caller can decide how to handle startup errors.
        raise RuntimeError(f"Invalid environment configuration: {exc}") from exc
