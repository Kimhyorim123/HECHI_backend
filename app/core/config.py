from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # DB URL (환경변수: DATABASE_URL)
    database_url: Optional[str] = Field(
        default="sqlite:///./dev.db",
        validation_alias="DATABASE_URL",
    )
    # 기본 설정들
    environment: str = Field(default="local")
    secret_key: str = Field(default="CHANGE_ME_SECRET")
    access_token_exp_minutes: int = Field(default=1440)  # 24시간
    refresh_token_exp_days: int = Field(default=14)
    jwt_algorithm: str = Field(default="HS256")

    # 외부 API/서비스 키
    google_books_api_key: Optional[str] = Field(
        default=None,
        validation_alias="GOOGLE_BOOKS_API_KEY",
    )

    aladin_api_key: Optional[str] = Field(
        default=None,
        validation_alias="ALADIN_API_KEY",
    )

    openai_api_key: Optional[str] = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )

    fcm_service_account_json_path: Optional[str] = None

    # CORS
    cors_origins: str = Field(default="*")  # comma separated list for production

    # AWS/S3
    aws_access_key_id: Optional[str] = Field(
        default=None,
        validation_alias="AWS_ACCESS_KEY_ID",
    )
    aws_secret_access_key: Optional[str] = Field(
        default=None,
        validation_alias="AWS_SECRET_ACCESS_KEY",
    )
    aws_region: Optional[str] = Field(
        default=None,
        validation_alias="AWS_REGION",
    )
    s3_bucket: Optional[str] = Field(
        default=None,
        validation_alias="S3_BUCKET",
    )
    s3_public_base_url: Optional[str] = Field(
        default=None,
        validation_alias="S3_PUBLIC_BASE_URL",
    )  # e.g., https://cdn.example.com/

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="forbid",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
