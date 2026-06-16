import os

# Set ONNX Runtime logging and provider environment variables early to suppress device discovery warnings
os.environ["ORT_LOGGING_LEVEL"] = "3"
os.environ["ONNXRUNTIME_PROVIDERS"] = '["CPUExecutionProvider"]'

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices, field_validator, model_validator
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()



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
    SECRET_KEY: str = Field(
        default="dev-secret-key-change-in-production",
        validation_alias=AliasChoices("JWT_SECRET", "SECRET_KEY", "JWT_SECRET_KEY")
    )
    JWT_REFRESH_SECRET: str = Field(
        default="dev-refresh-secret-key-change-in-production",
        validation_alias=AliasChoices("JWT_REFRESH_SECRET", "REFRESH_SECRET_KEY")
    )
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
    GEMINI_API_KEY: str = ""
    HUGGINGFACE_TOKEN: str = Field(
        default="",
        validation_alias=AliasChoices("HUGGINGFACE_TOKEN", "HF_TOKEN")
    )
    HF_TOKEN: str = Field(
        default="",
        validation_alias=AliasChoices("HF_TOKEN", "HUGGINGFACE_TOKEN")
    )
    TESSERACT_PATH: str = ""

    # Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 500

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # CORS
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        validation_alias=AliasChoices("CORS_ORIGINS", "ALLOWED_ORIGINS")
    )

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def parse_secret_key(cls, v):
        if not v or v == "dev-secret-key-change-in-production":
            persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
            os.makedirs(persist_dir, exist_ok=True)
            key_path = os.path.join(persist_dir, "secret.key")
            if os.path.exists(key_path):
                try:
                    with open(key_path, "r") as f:
                        saved_key = f.read().strip()
                        if saved_key:
                            return saved_key
                except Exception:
                    pass
            import secrets
            new_key = secrets.token_hex(32)
            try:
                with open(key_path, "w") as f:
                    f.write(new_key)
            except Exception:
                pass
            return new_key
        return v

    @field_validator("JWT_REFRESH_SECRET", mode="before")
    @classmethod
    def parse_refresh_secret(cls, v):
        if not v or v == "dev-refresh-secret-key-change-in-production":
            persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
            os.makedirs(persist_dir, exist_ok=True)
            key_path = os.path.join(persist_dir, "refresh_secret.key")
            if os.path.exists(key_path):
                try:
                    with open(key_path, "r") as f:
                        saved_key = f.read().strip()
                        if saved_key:
                            return saved_key
                except Exception:
                    pass
            import secrets
            new_key = secrets.token_hex(32)
            try:
                with open(key_path, "w") as f:
                    f.write(new_key)
            except Exception:
                pass
            return new_key
        return v

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

    @model_validator(mode="after")
    def set_redis_defaults(self) -> 'Settings':
        if self.REDIS_URL != "redis://localhost:6379/0":
            if not self.CELERY_BROKER_URL or self.CELERY_BROKER_URL == "redis://localhost:6379/0":
                self.CELERY_BROKER_URL = self.REDIS_URL
            if not self.CELERY_RESULT_BACKEND or self.CELERY_RESULT_BACKEND == "redis://localhost:6379/0":
                self.CELERY_RESULT_BACKEND = self.REDIS_URL
        return self


settings = Settings()

# Ensure upload dir
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
