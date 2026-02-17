"""
Production-hardened application configuration with startup validation.

IMPROVEMENTS FROM V5:
- Fail-fast validation on startup
- Environment-specific settings
- Structured configuration classes
- Resource limit enforcement
- Security-first defaults

FIXES APPLIED:
- Default SECRET_KEY is now >= 32 chars to pass validation in development
- validate_configuration() no longer calls sys.exit() directly; raises instead
"""
import os
import logging
from pathlib import Path
from typing import List, Set

logger = logging.getLogger(__name__)

# ============================================================================
# BASE PATHS
# ============================================================================

BASE_DIR = Path(__file__).parent.parent
STORAGE_DIR = BASE_DIR / "storage"
RAW_STORAGE_DIR = STORAGE_DIR / "raw"

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"
IS_DEVELOPMENT = ENVIRONMENT == "development"

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if IS_PRODUCTION:
        logger.critical("DATABASE_URL environment variable is required in production")
        raise RuntimeError("DATABASE_URL not set in production")
    else:
        DATABASE_URL = "mysql+pymysql://root:password@db:3306/policycheck"
        logger.critical(
            "Using default DATABASE_URL for development (INSECURE default credentials). "
            "Set DATABASE_URL explicitly before production deployment."
        )

# Connection pool settings
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))

# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if IS_PRODUCTION:
        logger.critical(
            "SECRET_KEY environment variable is REQUIRED in production! "
            "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
        raise RuntimeError("SECRET_KEY not set in production")
    else:
        # Must be >= 32 characters to pass startup validation
        SECRET_KEY = "dev-insecure-key-DO-NOT-USE-IN-PRODUCTION-PADDING"
        logger.critical(
            "Using insecure SECRET_KEY for development. "
            "Tokens are not safe for production."
        )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
DOWNLOAD_TOKEN_EXPIRE_MINUTES = int(os.getenv("DOWNLOAD_TOKEN_EXPIRE_MINUTES", "5"))  # 5 minutes for downloads

# ============================================================================
# CORS CONFIGURATION
# ============================================================================

CORS_ORIGINS_STR = os.getenv(
    "CORS_ORIGINS",
    "http://localhost,http://localhost:80,http://localhost:5173,http://localhost:3000"
)
CORS_ORIGINS: List[str] = [origin.strip() for origin in CORS_ORIGINS_STR.split(",")]

if IS_PRODUCTION and "localhost" in CORS_ORIGINS_STR:
    logger.warning("CORS origins include localhost in production - verify this is intended")

# ============================================================================
# CRAWL CONFIGURATION
# ============================================================================

# Page limits
MAX_PAGES_DEFAULT = int(os.getenv("MAX_PAGES_DEFAULT", "1000"))
MAX_PAGES_ABSOLUTE = int(os.getenv("MAX_PAGES_ABSOLUTE", "500000"))  # Increased to 500k for large crawls

# Time limits
MAX_MINUTES_DEFAULT = int(os.getenv("MAX_MINUTES_DEFAULT", "60"))
MAX_MINUTES_ABSOLUTE = int(os.getenv("MAX_MINUTES_ABSOLUTE", "180"))  # 3 hours hard limit

# Request behavior
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.5"))  # seconds between requests
CRAWL_CONNECT_TIMEOUT = float(os.getenv("CRAWL_CONNECT_TIMEOUT", "5"))  # seconds
CRAWL_READ_TIMEOUT = float(os.getenv("CRAWL_READ_TIMEOUT", "30"))  # seconds
CRAWL_TOTAL_TIMEOUT = float(os.getenv("CRAWL_TOTAL_TIMEOUT", "60"))  # seconds
# Backward compatibility alias; use CRAWL_TOTAL_TIMEOUT for new code.
CRAWL_TIMEOUT = CRAWL_TOTAL_TIMEOUT
CRAWL_MAX_RETRIES = int(os.getenv("CRAWL_MAX_RETRIES", "3"))
USER_AGENT = os.getenv("USER_AGENT", "PolicyCheckBot/6.0 (+https://policycheck.io/bot)")

# Concurrency control - CRITICAL FIX
MAX_CONCURRENT_CRAWLS = int(os.getenv("MAX_CONCURRENT_CRAWLS", "3"))

# Robots.txt bypass for testing
CRAWL_RESPECT_ROBOTS = os.getenv("CRAWL_RESPECT_ROBOTS", "true").lower() == "true"

# Crawl strategy: "breadth" for BFS (better diversity) or "depth" for DFS (deeper exploration)
CRAWL_MODE = os.getenv("CRAWL_MODE", "breadth").lower()
# Max concurrent PDF downloads per crawl session
CRAWL_PDF_CONCURRENCY = int(os.getenv("CRAWL_PDF_CONCURRENCY", "5"))

# ============================================================================
# FILE HANDLING CONFIGURATION
# ============================================================================

MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "8192"))
MAX_DOWNLOAD_TIME = int(os.getenv("MAX_DOWNLOAD_TIME", "300"))  # 5 minutes max per file

# ============================================================================
# URL NORMALIZATION
# ============================================================================

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
    'gclid', 'fbclid', 'ref', 'v', 'version', 'format', 'source',
    'gclsrc', 'dclid', '_ga', 'mc_cid', 'mc_eid', 'msclkid'
}

# ============================================================================
# RATE LIMITING
# ============================================================================

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_CRAWL_START = int(os.getenv("RATE_LIMIT_CRAWL_START", "5"))  # requests per minute
RATE_LIMIT_DELAY_MIN = float(os.getenv("RATE_LIMIT_DELAY_MIN", "0.5"))
RATE_LIMIT_DELAY_MAX = float(os.getenv("RATE_LIMIT_DELAY_MAX", "2.0"))

# API request rate limiting (security middleware)
API_RATE_LIMIT_ENABLED = os.getenv(
    "API_RATE_LIMIT_ENABLED",
    "true" if RATE_LIMIT_ENABLED else "false"
).lower() == "true"
API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE = int(
    os.getenv("API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE", "60")
)
API_RATE_LIMIT_ANONYMOUS_PER_MINUTE = int(
    os.getenv("API_RATE_LIMIT_ANONYMOUS_PER_MINUTE", "30")
)
API_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60"))
API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = int(
    os.getenv("API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS", "30")
)
API_RATE_LIMIT_EXEMPT_PATHS_STR = os.getenv(
    "API_RATE_LIMIT_EXEMPT_PATHS",
    "/health,/health/liveness,/health/readiness,/ready,/metrics,/docs,/redoc,/openapi.json"
)
API_RATE_LIMIT_EXEMPT_PATHS: Set[str] = {
    path.strip()
    for path in API_RATE_LIMIT_EXEMPT_PATHS_STR.split(",")
    if path.strip()
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if IS_PRODUCTION else "DEBUG")
LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - "
    "[%(filename)s:%(lineno)d] - %(message)s"
)
LOG_JSON_FORMAT = os.getenv("LOG_JSON_FORMAT", "false").lower() == "true"

# ============================================================================
# MONITORING & METRICS
# ============================================================================

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").lower() == "true"
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

# ============================================================================
# CACHE & REDIS
# ============================================================================

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_DEFAULT_TTL_SECONDS = int(os.getenv("CACHE_DEFAULT_TTL_SECONDS", "60"))
CACHE_KEY_PREFIX = os.getenv("CACHE_KEY_PREFIX", "policycheck")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"
REDIS_SOCKET_TIMEOUT_SECONDS = float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "1.5"))

# ============================================================================
# STARTUP VALIDATION
# ============================================================================

def validate_configuration() -> None:
    """
    Validate configuration on startup.
    Fail fast if critical settings are missing or invalid.
    
    CHANGES:
    - Raises RuntimeError instead of sys.exit() so callers can handle it
    - In development, SECRET_KEY length is a warning, not a fatal error
    """
    errors = []
    warnings = []
    
    # Validate SECRET_KEY strength
    if len(SECRET_KEY) < 32:
        if IS_PRODUCTION:
            errors.append(f"SECRET_KEY too short ({len(SECRET_KEY)} chars, minimum 32)")
        else:
            warnings.append(f"SECRET_KEY is short ({len(SECRET_KEY)} chars) - acceptable in development")
    
    # Validate database URL format
    if not DATABASE_URL.startswith(("mysql+pymysql://", "postgresql://")):
        errors.append(f"Invalid DATABASE_URL format: {DATABASE_URL[:20]}...")
    
    # Validate storage directories
    try:
        RAW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        if not RAW_STORAGE_DIR.is_dir():
            errors.append(f"Storage directory is not a directory: {RAW_STORAGE_DIR}")
    except Exception as e:
        errors.append(f"Cannot create storage directory: {e}")
    
    # Validate numeric ranges
    if MAX_CONCURRENT_CRAWLS < 1 or MAX_CONCURRENT_CRAWLS > 20:
        errors.append(f"MAX_CONCURRENT_CRAWLS out of range: {MAX_CONCURRENT_CRAWLS} (must be 1-20)")
    
    if MAX_FILE_SIZE_MB < 1 or MAX_FILE_SIZE_MB > 500:
        errors.append(f"MAX_FILE_SIZE_MB out of range: {MAX_FILE_SIZE_MB} (must be 1-500)")

    if CRAWL_CONNECT_TIMEOUT <= 0:
        errors.append("CRAWL_CONNECT_TIMEOUT must be > 0")

    if CRAWL_READ_TIMEOUT <= 0:
        errors.append("CRAWL_READ_TIMEOUT must be > 0")

    if CRAWL_TOTAL_TIMEOUT <= 0:
        errors.append("CRAWL_TOTAL_TIMEOUT must be > 0")

    if CRAWL_TOTAL_TIMEOUT < max(CRAWL_CONNECT_TIMEOUT, CRAWL_READ_TIMEOUT):
        errors.append(
            "CRAWL_TOTAL_TIMEOUT must be >= max(CRAWL_CONNECT_TIMEOUT, CRAWL_READ_TIMEOUT)"
        )

    if CRAWL_MAX_RETRIES < 0 or CRAWL_MAX_RETRIES > 10:
        errors.append("CRAWL_MAX_RETRIES out of range (must be 0-10)")
    
    # Validate cache/redis configuration
    if CACHE_DEFAULT_TTL_SECONDS < 1 or CACHE_DEFAULT_TTL_SECONDS > 86400:
        errors.append(
            "CACHE_DEFAULT_TTL_SECONDS out of range "
            f"({CACHE_DEFAULT_TTL_SECONDS}; must be 1-86400)"
        )

    if REDIS_PORT < 1 or REDIS_PORT > 65535:
        errors.append(f"REDIS_PORT out of range: {REDIS_PORT}")

    if REDIS_DB < 0 or REDIS_DB > 15:
        warnings.append(f"REDIS_DB is unusual ({REDIS_DB}); verify Redis config")

    if REDIS_SOCKET_TIMEOUT_SECONDS <= 0:
        errors.append("REDIS_SOCKET_TIMEOUT_SECONDS must be > 0")

    # Validate API rate limiting
    if API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE < 1:
        errors.append(
            "API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE must be >= 1"
        )

    if API_RATE_LIMIT_ANONYMOUS_PER_MINUTE < 1:
        errors.append(
            "API_RATE_LIMIT_ANONYMOUS_PER_MINUTE must be >= 1"
        )

    if API_RATE_LIMIT_WINDOW_SECONDS < 1 or API_RATE_LIMIT_WINDOW_SECONDS > 3600:
        errors.append(
            f"API_RATE_LIMIT_WINDOW_SECONDS out of range: {API_RATE_LIMIT_WINDOW_SECONDS} (must be 1-3600)"
        )

    if (
        API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS < 1
        or API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS > 3600
    ):
        errors.append(
            "API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS out of range: "
            f"{API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS} (must be 1-3600)"
        )

    invalid_exempt_paths = [
        path for path in API_RATE_LIMIT_EXEMPT_PATHS if not path.startswith("/")
    ]
    if invalid_exempt_paths:
        errors.append(
            f"API_RATE_LIMIT_EXEMPT_PATHS must contain absolute paths only: {invalid_exempt_paths}"
        )
    
    # Production-specific validation
    if IS_PRODUCTION:
        if "insecure" in SECRET_KEY.lower() or "dev" in SECRET_KEY.lower():
            errors.append("SECRET_KEY appears to be a development key in production")
        
        if not API_RATE_LIMIT_ENABLED:
            warnings.append("API rate limiting disabled in production - verify this is intended")
    
    # Report warnings
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")
    
    # Report errors
    if errors:
        logger.critical("Configuration validation failed:")
        for error in errors:
            logger.critical(f"  - {error}")
        raise RuntimeError(f"Configuration validation failed: {'; '.join(errors)}")
    
    logger.info("Configuration validation passed")
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info(f"Max concurrent crawls: {MAX_CONCURRENT_CRAWLS}")
    logger.info(f"API rate limiting: {'enabled' if API_RATE_LIMIT_ENABLED else 'disabled'}")
    logger.info(f"Storage directory: {RAW_STORAGE_DIR}")


# ============================================================================
# EXPORT CONFIGURATION
# ============================================================================

__all__ = [
    # Environment
    'ENVIRONMENT', 'IS_PRODUCTION', 'IS_DEVELOPMENT',
    
    # Database
    'DATABASE_URL', 'DB_POOL_SIZE', 'DB_MAX_OVERFLOW', 
    'DB_POOL_TIMEOUT', 'DB_POOL_RECYCLE',
    
    # Security
    'SECRET_KEY', 'ALGORITHM', 'ACCESS_TOKEN_EXPIRE_MINUTES',
    'DOWNLOAD_TOKEN_EXPIRE_MINUTES',
    
    # CORS
    'CORS_ORIGINS',
    
    # Crawl
    'MAX_PAGES_DEFAULT', 'MAX_PAGES_ABSOLUTE',
    'MAX_MINUTES_DEFAULT', 'MAX_MINUTES_ABSOLUTE',
    'REQUEST_DELAY',
    'CRAWL_CONNECT_TIMEOUT', 'CRAWL_READ_TIMEOUT', 'CRAWL_TOTAL_TIMEOUT',
    'CRAWL_TIMEOUT', 'CRAWL_MAX_RETRIES',
    'USER_AGENT', 'MAX_CONCURRENT_CRAWLS',
    'CRAWL_RESPECT_ROBOTS',
    'CRAWL_MODE', 'CRAWL_PDF_CONCURRENCY',
    
    # Files
    'MAX_FILE_SIZE_MB', 'MAX_FILE_SIZE_BYTES', 
    'CHUNK_SIZE', 'MAX_DOWNLOAD_TIME',
    'RAW_STORAGE_DIR', 'STORAGE_DIR',
    
    # Rate limiting
    'RATE_LIMIT_ENABLED', 'RATE_LIMIT_CRAWL_START',
    'RATE_LIMIT_DELAY_MIN', 'RATE_LIMIT_DELAY_MAX',
    'API_RATE_LIMIT_ENABLED',
    'API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE',
    'API_RATE_LIMIT_ANONYMOUS_PER_MINUTE',
    'API_RATE_LIMIT_WINDOW_SECONDS',
    'API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS',
    'API_RATE_LIMIT_EXEMPT_PATHS',
    
    # Logging
    'LOG_LEVEL', 'LOG_FORMAT', 'LOG_JSON_FORMAT',
    
    # Monitoring
    'METRICS_ENABLED', 'METRICS_PORT',

    # Cache/Redis
    'CACHE_ENABLED', 'CACHE_DEFAULT_TTL_SECONDS', 'CACHE_KEY_PREFIX',
    'REDIS_HOST', 'REDIS_PORT', 'REDIS_DB', 'REDIS_PASSWORD', 'REDIS_SSL',
    'REDIS_SOCKET_TIMEOUT_SECONDS',
    
    # URL normalization
    'TRACKING_PARAMS',
    
    # Validation
    'validate_configuration',
]
