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
    """Path to Markdown file: canonical additional (professional) experience for resume tailoring."""
    additional_experience_path: str = ""
    """Path to Markdown file: educational roles (TA, lab, assistantships) for resume tailoring."""
    educational_experience_path: str = ""
    """Path to Markdown file: projects for resume tailoring."""
    projects_path: str = ""
    """Path to Markdown file: contact, education, achievements for resume tailoring."""
    resume_details_path: str = ""
    """Path to LaTeX file: fixed resume layout (preamble, macros, section style) for tailored output."""
    resume_blueprint_tex_path: str = ""
    """Anthropic API key for resume/cover LaTeX generation (or reuse Bearer from custom AI if unset)."""
    anthropic_api_key: str = ""
    """Model id for resume/cover generation, e.g. claude-sonnet-4-20250514."""
    anthropic_resume_model: str = "claude-sonnet-4-20250514"
    """pdflatex binary name or path."""
    pdflatex_path: str = "pdflatex"
    """Telegram Bot API token (optional: job listing summary after /json)."""
    telegram_bot_token: str = ""
    """Telegram chat id to receive job listing summaries."""
    telegram_chat_id: str = ""
    """Optional Cloudflare Browser Rendering custom AI model (e.g. anthropic/claude-sonnet-4-20250514)."""
    job_detail_custom_ai_model: str = ""
    """Authorization header value for custom AI provider, e.g. 'Bearer <API_KEY>'."""
    job_detail_custom_ai_authorization: str = ""

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
