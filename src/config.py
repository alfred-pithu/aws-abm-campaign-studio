"""Environment and filesystem configuration.

Secrets stay in `.env` locally or Streamlit Cloud secrets. Nothing here hardcodes API keys.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "aws-abm-poc"
    validation_repair_max_attempts: int = 3

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "data"

    @property
    def assets_dir(self) -> Path:
        return PROJECT_ROOT / "assets"

    @property
    def templates_dir(self) -> Path:
        return PROJECT_ROOT / "templates"

    @property
    def output_dir(self) -> Path:
        return PROJECT_ROOT / "output"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "campaigns.db"


def _apply_streamlit_secrets() -> None:
    """Copy Streamlit Cloud secrets into env vars for pydantic-settings."""
    try:
        import streamlit as st

        secrets = st.secrets
    except Exception:
        return
    pairs = (
        ("OPENAI_API_KEY", ("OPENAI_API_KEY", "openai_api_key")),
        ("OPENAI_BASE_URL", ("OPENAI_BASE_URL", "openai_base_url")),
        ("OPENAI_MODEL", ("OPENAI_MODEL", "openai_model")),
    )
    for env_name, keys in pairs:
        if os.environ.get(env_name):
            continue
        for key in keys:
            try:
                value = secrets[key]
            except Exception:
                continue
            if value:
                os.environ[env_name] = str(value)
                break


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _apply_streamlit_secrets()
    return Settings()


DEMO_BRIEF = {
    "product": "Amazon Bedrock",
    "audience": "CTOs at AI startups",
    "goal": "Drive awareness",
    "channel": "email",
    "tone": "Technical, confident, practical",
    "key_message": (
        "Help engineering teams build generative AI applications using managed "
        "foundation model capabilities."
    ),
    "additional_context": "",
}

DEMO_REQUEST = (
    "Promote Amazon Bedrock to CTOs at AI startups. I need an email to drive awareness. "
    "Keep the tone technical, confident, and practical. Help engineering teams build "
    "generative AI applications using managed foundation model capabilities."
)
