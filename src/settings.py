from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_token: str = ""
    telegram_chat_id: str = ""
    webhook_secret: str = "changeme"
    log_level: str = "INFO"
    dry_run_notify_only: bool = False
    github_token: str = ""
    github_repo: str = ""           # e.g. noetar-create/previousdaybot
    github_log_path: str = "trades/trades.csv"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def settings() -> Settings:
    return Settings()
