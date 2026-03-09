from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    patreon_client_id: str
    patreon_client_secret: str
    patreon_redirect_uri: str
    patreon_campaign_id: str
    # Comma-separated tier titles that grant access, e.g. "Gold,Platinum"
    paid_tier: str
    # Random secret used to sign CSRF state tokens
    secret_key: str
    # Directory where protected files are stored
    files_dir: str = "./files"
    db_url: str = "sqlite+aiosqlite:///./cdn.db"
    # Set to False in local dev (allows non-HTTPS cookies)
    cookie_secure: bool = True
    # Max requests per minute per IP on /access/ routes
    rate_limit_per_minute: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
