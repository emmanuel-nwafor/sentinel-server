import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_ENV_FILES = (_BACKEND_DIR / ".env", ".env")


class Settings(BaseSettings):
    PROJECT_NAME: str = "Dispatch AI Operations Platform"
    VERSION: str = "0.3.0"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # PostgreSQL Database URL
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sentinel_db"
    # Fallback SQLite Async for local testing when Postgres is not running locally
    SQLITE_FALLBACK_URL: str = "sqlite+aiosqlite:///./sentinel.db"

    # Security & Auth
    JWT_SECRET: str = "sentinel_super_secret_jwt_key_2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    TOKEN_ENCRYPTION_KEY: str = ""  # Optional Fernet key; derives from JWT_SECRET in dev if empty

    # Email & OTP Verification
    RESEND_API_KEY: str = ""
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = ""
    EMAIL_FROM: str = "Dispatch <noreply@dispatch.io>"
    OTP_EXPIRE_MINUTES: int = 10
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_MAX_ATTEMPTS: int = 5

    # LLM Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    OPENAI_API_KEY: str = ""

    # Monetization & Premium Feature Flags
    # By default, enforcement is disabled (False) so all users have unrestricted access in dev/early-stage
    ENABLE_PREMIUM_ENFORCEMENT: bool = False
    DEFAULT_FREE_AI_QUOTA: int = 50
    PRO_TIER_MONTHLY_PRICE: float = 29.0
    ENTERPRISE_TIER_MONTHLY_PRICE: float = 99.0

    # Redis & Task Queue
    REDIS_URL: str = "redis://localhost:6379"

    # Cloudinary & Mux Tools
    CLOUDINARY_CLOUD_NAME: str = "sentinel_demo_cloud"
    CLOUDINARY_API_KEY: str = "123456789012345"
    CLOUDINARY_API_SECRET: str = "sentinel_cloudinary_secret_key"
    MUX_TOKEN_ID: str = "sentinel_mux_token_id"
    MUX_TOKEN_SECRET: str = "sentinel_mux_token_secret"
    MUX_SIGNING_KEY: str = ""

    # Cloudflare R2 Object Storage (Zero-egress S3-compatible media engine)
    CLOUDFLARE_R2_ACCOUNT_ID: str = ""
    CLOUDFLARE_R2_ACCESS_KEY_ID: str = ""
    CLOUDFLARE_R2_SECRET_ACCESS_KEY: str = ""
    CLOUDFLARE_R2_BUCKET_NAME: str = "dispatch-media"
    CLOUDFLARE_R2_PUBLIC_URL: str = ""

    # Social Login & Publishing OAuth App Credentials (app-level keys, not user tokens)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = (
        "https://dispatch-6mlh.onrender.com/api/v1/auth/oauth/google/callback"
    )

    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    LINKEDIN_REDIRECT_URI: str = (
        "https://dispatch-6mlh.onrender.com/api/v1/social/callback/linkedin"
    )
    LINKEDIN_API_VERSION: str = "202611"

    X_CLIENT_ID: str = ""
    X_CLIENT_SECRET: str = ""
    X_REDIRECT_URI: str = "https://dispatch-6mlh.onrender.com/api/v1/social/callback/x"
    X_API_KEY: str = ""
    X_API_SECRET: str = ""
    X_BEARER_TOKEN: str = ""
    X_ACCESS_TOKEN: str = ""
    X_ACCESS_SECRET: str = ""

    META_APP_ID: str = "1650463666534776"
    META_APP_SECRET: str = ""
    META_CONFIG_ID: str = "1886402302343483"
    META_REDIRECT_URI: str = (
        "https://dispatch-6mlh.onrender.com/api/v1/social/callback/instagram"
    )
    META_GRAPH_API_VERSION: str = "v21.0"

    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REDIRECT_URI: str = (
        "https://dispatch-6mlh.onrender.com/api/v1/social/callback/youtube"
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore")


settings = Settings()
