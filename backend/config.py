from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices, field_validator
from typing import List, Optional
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    # App
    APP_NAME: str = "Personal AI Studio"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = Field(
        default="aistudio",
        validation_alias=AliasChoices("DATABASE_NAME", "MONGODB_DB_NAME")
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # AI
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_MODEL: str = "llama3"
    OPENAI_API_KEY: str = ""
    HUGGINGFACE_TOKEN: str = ""

    # Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 500

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # CORS
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        validation_alias=AliasChoices("CORS_ORIGINS", "ALLOWED_ORIGINS")
    )

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            val = v.strip().lower()
            if val in ("true", "1", "yes", "on", "t", "debug", "development"):
                return True
            if val in ("false", "0", "no", "off", "f", "production"):
                return False
            return False
        return bool(v)

    @field_validator(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "REFRESH_TOKEN_EXPIRE_DAYS",
        "MAX_UPLOAD_SIZE_MB",
        "RATE_LIMIT_PER_MINUTE",
        mode="before"
    )
    @classmethod
    def parse_ints(cls, v, info):
        if v == "" or v is None:
            defaults = {
                "ACCESS_TOKEN_EXPIRE_MINUTES": 60,
                "REFRESH_TOKEN_EXPIRE_DAYS": 30,
                "MAX_UPLOAD_SIZE_MB": 500,
                "RATE_LIMIT_PER_MINUTE": 60
            }
            return defaults.get(info.field_name, 60)
        try:
            return int(v)
        except (ValueError, TypeError):
            defaults = {
                "ACCESS_TOKEN_EXPIRE_MINUTES": 60,
                "REFRESH_TOKEN_EXPIRE_DAYS": 30,
                "MAX_UPLOAD_SIZE_MB": 500,
                "RATE_LIMIT_PER_MINUTE": 60
            }
            return defaults.get(info.field_name, 60)

    @property
    def allowed_origins_list(self) -> List[str]:
        if not self.ALLOWED_ORIGINS:
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()

# Ensure upload dir
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
