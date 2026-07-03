"""Central configuration via environment variables (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from env vars / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    strqc_db_path: str = "./str_qc.sqlite"
    strqc_master_key: str = ""  # base64, 32 bytes — required for secret encryption
    strqc_photo_dir: str = "./photostore"

    # BIDI voice model selection: gemini | openai | nova
    strqc_bidi_provider: str = "gemini"

    # Gemini
    google_api_key: str = ""
    strqc_gemini_model_id: str = "gemini-3.1-flash-live-preview"

    # OpenAI Realtime
    openai_api_key: str = ""
    openai_organization: str = ""
    openai_project: str = ""
    openai_model: str = "gpt-realtime-2"

    # Amazon Nova Sonic (Bedrock; credentials come from the AWS chain)
    strqc_nova_model_id: str = "amazon.nova-2-sonic-v1:0"
    aws_region: str = "us-east-1"

    # Google credentials for strands-google tools (use_google):
    # service-account key path (primary) or OAuth token path (alternative).
    google_application_credentials: str = ""
    google_oauth_credentials: str = ""

    # Slack (Addendum 1)
    slack_bot_token: str = ""
    slack_default_channel_id: str = ""

    # Escapia (Addendum 2)
    escapia_base_url: str = "https://hsapi.escapia.com/dragomanadapter"
    escapia_client_id: str = ""
    escapia_client_secret: str = ""
    escapia_pmc_id: str = ""
    escapia_api_version: str = "1"
    escapia_end_system: str = "EscapiaVRS"

    # API
    strqc_api_host: str = "0.0.0.0"
    strqc_api_port: int = 8000
    strqc_session_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
