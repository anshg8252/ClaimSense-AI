"""Configuration module for ClaimSense AI backend (Hardened)."""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Base directory is project root
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root if it exists
load_dotenv(BASE_DIR / ".env")

KNOWN_INSECURE_SECRETS = {
    "claimsense-ai-dev-secret-key-change-in-production",
    "secret",
    "secret_key",
    "changeme",
    "dev",
    "12345",
    "test",
    "password",
}


class Config:
    """Base application configuration with environment security controls."""

    KNOWN_INSECURE_SECRETS = KNOWN_INSECURE_SECRETS

    # Project paths
    BASE_DIR = BASE_DIR
    BACKEND_DIR = BASE_DIR / "backend"
    FRONTEND_DIR = BASE_DIR / "frontend"
    UPLOAD_FOLDER = BASE_DIR / os.getenv("UPLOAD_FOLDER", "uploads")
    REPORTS_FOLDER = BASE_DIR / os.getenv("REPORTS_FOLDER", "reports")
    DATA_FOLDER = BASE_DIR / "data"

    # Environment & Debug settings
    FLASK_ENV = os.getenv("FLASK_ENV", "development").strip().lower()
    DEBUG = os.getenv("FLASK_DEBUG", "True").strip().lower() in ("true", "1", "yes")
    IS_PRODUCTION = (FLASK_ENV == "production" or not DEBUG)

    # Server binding settings
    HOST = os.getenv("HOST", "127.0.0.1").strip()
    try:
        PORT = int(os.getenv("PORT", 5000))
        if not (1 <= PORT <= 65535):
            raise ValueError()
    except (ValueError, TypeError):
        PORT = 5000

    # Secret Key enforcement
    _raw_secret = os.getenv("SECRET_KEY", "").strip()
    if IS_PRODUCTION:
        if not _raw_secret or _raw_secret in KNOWN_INSECURE_SECRETS or len(_raw_secret) < 16:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: A strong, unique SECRET_KEY (minimum 16 characters) "
                "must be configured in the environment for production operation. Refusing to start with "
                "missing, weak, or default secret."
            )
        SECRET_KEY = _raw_secret
    else:
        SECRET_KEY = _raw_secret if _raw_secret else "dev-insecure-secret-key-claimsense-ai-local-only"

    # CORS Allowed Origins
    CORS_ALLOWED_ORIGINS = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:5000,http://localhost:5000,http://127.0.0.1:5001,http://localhost:5001",
    )

    # Upload constraints
    try:
        MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))
        if MAX_CONTENT_LENGTH <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB default

    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx"}

    # Database Configuration
    DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "data/claimsense.db")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH.as_posix()}")

    # Session & Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION  # Enforce HTTPS-only cookie transmission in production

    # CSRF Security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True

    # Rate Limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"

    # Risk thresholds
    try:
        RISK_THRESHOLD_LOW = int(os.getenv("RISK_THRESHOLD_LOW", 30))
    except (ValueError, TypeError):
        RISK_THRESHOLD_LOW = 30

    try:
        RISK_THRESHOLD_MEDIUM = int(os.getenv("RISK_THRESHOLD_MEDIUM", 60))
    except (ValueError, TypeError):
        RISK_THRESHOLD_MEDIUM = 60

    # LLM Settings (Placeholder for Phase 9)
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")

    # Phase 12: Asynchronous Task Queue & Worker Configuration
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    ASYNC_PROCESSING_ENABLED = os.getenv("ASYNC_PROCESSING_ENABLED", "false").strip().lower() in ("true", "1", "yes")
    QUEUE_BROKER_TYPE = os.getenv("QUEUE_BROKER_TYPE", "auto").strip().lower()  # auto, redis, threaded
    try:
        TASK_MAX_RETRIES = int(os.getenv("TASK_MAX_RETRIES", "3"))
    except (ValueError, TypeError):
        TASK_MAX_RETRIES = 3
    try:
        TASK_TIMEOUT_SECONDS = int(os.getenv("TASK_TIMEOUT_SECONDS", "300"))
    except (ValueError, TypeError):
        TASK_TIMEOUT_SECONDS = 300

    @classmethod
    def ensure_directories(cls):
        """Ensure necessary runtime directories exist."""
        cls.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.DATA_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
