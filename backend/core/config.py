"""Application settings — loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "dev"
    log_level: str = "INFO"
    allowed_origins: list[str] = []

    # Azure AD (optional - falls back to JWT when not set)
    azure_ad_tenant_id: str = ""
    azure_ad_client_id: str = ""
    azure_ad_client_secret: str = ""
    azure_ad_redirect_uri: str = ""

    # Auth (JWT - used when Azure AD not configured)
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # PostgreSQL
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mortgage_intelligence"

    # Encompass (customer's LOS)
    encompass_instance_url: str = ""
    encompass_client_id: str = ""
    encompass_client_secret: str = ""
    encompass_webhook_secret: str = ""

    # Storage (cloud-agnostic, default MinIO for self-hosted)
    storage_provider: str = "s3"
    storage_bucket: str = "mortgage-processor-docs"
    storage_region: str = "us-east-1"
    storage_endpoint_url: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"

    # LLM Provider (default: Ollama - open-source, local)
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434"
    llm_default_model: str = "llama3.1"
    llm_vision_model: str = "llava"
    llm_api_key: str = ""

    # Anthropic / Claude (optional cloud LLM)
    anthropic_api_key: str = ""

    # Langfuse (open-source observability, self-hosted)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"

    # Azure Blob Storage (optional)
    azure_storage_connection_string: str = ""
    azure_storage_container: str = ""

    # DeepEval / Confident AI
    deepeval_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
