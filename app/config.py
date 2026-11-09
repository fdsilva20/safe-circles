"""Safe Circles settings.

Everything is overridable from the environment or a `.env` file. Defaults are
for local development: SQLite, console email, no AI key.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # dev | prod
    app_name: str = "Safe Circles"
    database_url: str = "sqlite:///./safecircles.db"
    public_base_url: str = "http://localhost:8000"
    secret_key: str = "dev-only-change-me"

    # Comma-separated emails that become admins when they sign in.
    admin_emails: str = ""

    # Email. Empty smtp_host = console channel (prints the magic link).
    smtp_host: str = ""
    smtp_port: int = 587
    email_from: str = "noreply@example.org"
    email_from_name: str = "Safe Circles"

    # Privacy thresholds
    feedback_min_responses: int = 5  # aggregate feedback only above this per circle
    open_data_min_count: int = 3  # suppress per-city counts below this

    # AI helper for facilitators (optional). Uses the Anthropic SDK's own
    # credential resolution (ANTHROPIC_API_KEY or an `ant auth login` profile).
    ai_enabled: bool = True
    ai_model: str = "claude-opus-5-5"

    default_lang: str = "en"
    languages: str = "en,hi,mr"

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def language_list(self) -> list[str]:
        return [l.strip() for l in self.languages.split(",") if l.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
