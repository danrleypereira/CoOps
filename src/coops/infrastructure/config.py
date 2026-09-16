from typing import Literal
from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central typed settings, read from the environment, `.env` or `.secrets`.

    Every field is optional at load time so that commands which do not talk to
    GitHub (Silver/Gold processing, AI analysis) can still load settings.
    Commands that need a value validate it themselves (see
    `coops.etl.bronze_extract.main`).

    Env vars: GITHUB_TOKEN, GITHUB_ORG, GEMINI_API_KEY (or GOOGLE_API_KEY),
    GEMINI_MODEL, GITHUB_API_URL, COOPS_STORAGE, MONGO_URI, TENANT_MODE.
    """

    github_token: str | None = None
    github_org: str | None = None
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    # gemini-2.5-flash-lite is no longer available to new API keys.
    gemini_model: str = "gemini-3.5-flash-lite"
    # Placeholders for later phases; not read by the pipeline yet.
    github_api_url: str = "https://api.github.com"
    coops_storage: str = "data"
    mongo_uri: str | None = None
    tenant_mode: Literal["single", "multi"] = "single"

    model_config = SettingsConfigDict(
        env_file=(".env", ".secrets"),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
