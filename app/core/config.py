from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    environment: str = Field(default="local")
    secret_key: str = Field(default="CHANGE_ME_SECRET")
    access_token_exp_minutes: int = Field(default=30)
    refresh_token_exp_days: int = Field(default=14)
    jwt_algorithm: str = Field(default="HS256")

    database_url: str = Field(default="sqlite:///./dev.db")  # override with MySQL URL in .env
    openai_api_key: Optional[str] = None
    fcm_service_account_json_path: Optional[str] = None

    cors_origins: str = Field(default="*")  # comma separated list for production

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

@lru_cache
def get_settings() -> Settings:
    return Settings()
