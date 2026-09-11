from typing import Literal
from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    github_token: str
    github_org: str
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    github_api_url: str = "https://api.github.com"
    coops_storage: str = "data"
    mongo_uri: str | None = None
    tenant_mode: Literal["single", "multi"] = "single"


    model_config = SettingsConfigDict(
        env_file=(".env", ".secrets"),
        extra="ignore",)


@lru_cache
def get_settings() -> Settings:
    return Settings()


