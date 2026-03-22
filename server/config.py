from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cf_account_id: str = ""
    cf_api_token: str = ""
    """Optional raw ``Cookie`` header (good for quick tests; awkward for many/large cookies)."""
    handshake_cookie: str = ""
    """Path to JSON cookie file (see README). Empty = do not load from disk."""
    handshake_cookies_path: str = ""

    langchain_tracing_v2: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"),
    )
    langchain_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LANGCHAIN_API_KEY", "LANGSMITH_API_KEY"),
    )
    langchain_project: str = Field(
        default="apper",
        validation_alias=AliasChoices("LANGCHAIN_PROJECT", "LANGSMITH_PROJECT"),
    )
    langchain_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("LANGCHAIN_ENDPOINT", "LANGSMITH_ENDPOINT"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
