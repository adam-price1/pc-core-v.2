"""PolicyCheck v6 - Production-Hardened Ingestion Platform."""
import asyncio
import contextvars
import logging
import signal
import sys
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from jose import JWTError, jwt
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import validate_csrf_token
from app.cache import close_cache, get_cache_status, init_cache
from app.config import (
    ALGORITHM,
    API_RATE_LIMIT_ANONYMOUS_PER_MINUTE,
    API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE,
    API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
    API_RATE_LIMIT_ENABLED,
    API_RATE_LIMIT_EXEMPT_PATHS,
    API_RATE_LIMIT_WINDOW_SECONDS,
    CACHE_ENABLED,
    CORS_ORIGINS,
    IS_PRODUCTION,
    LOG_FORMAT,
    LOG_LEVEL,
    METRICS_ENABLED,
    RAW_STORAGE_DIR,
    SECRET_KEY,
    validate_configuration,
)
from app.database import (
    check_database_health,
    dispose_engine,
    get_pool_status,
    init_db,
)
from app.services import crawl_service
from app.routers import (
    audit_router,
    auth_router,
    crawl_router,
    documents_router,
    stats_router,
    system_router,
)

# ============================================================================
# LOGGING
# ============================================================================

_request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id",
    default="-",
)


class RequestIDLogFilter(logging.Filter):
    """Inject request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx_var.get("-")
        return True


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=f"{LOG_FORMAT} [request_id=%(request_id)s]",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

logger = logging.getLogger(__name__)

# Add filter to all loggers
for handler in logging.root.handlers:
    handler.addFilter(RequestIDLogFilter())

for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIDLogFilter())

if IS_PRODUCTION:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# ============================================================================
# METRICS
# ============================================================================

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)
http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently in progress",
    ["method", "endpoint"],
)

# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================

shutdown_event = False


def signal_handler(signum, frame):
    global shutdown_event
    logger.warning(f"Received {signal.Signals(signum).name}, shutting down...")
    shutdown_event = True


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ============================================================================
# RATE LIMITING
# ============================================================================


class InMemoryRateLimiter:
    """Simple in-memory sliding window limiter with async cleanup."""

    def __init__(self, window_seconds: int, cleanup_interval_seconds: int):
        self.window_seconds = window_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check_and_increment(self, key: str, limit: int) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        window_start = now - self.window_seconds

        async with self._lock:
            bucket = self._requests.setdefault(key, deque())

            while bucket and bucket[0] <= window_start:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after_seconds = max(1, int(bucket[0] + self.window_seconds - now + 0.999))
                return False, retry_after_seconds

            bucket.append(now)
            return True, 0

    async def cleanup_once(self) -> None:
        """Remove expired entries to prevent unbounded memory growth."""
        now = time.monotonic()
        window_start = now - self.window_seconds

        async with self._lock:
            keys_to_delete = []
            for key, bucket in self._requests.items():
                while bucket and bucket[0] <= window_start:
                    bucket.popleft()
                if not bucket:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._requests[key]

    async def cleanup_loop(self) -> None:
        """Background cleanup task for stale limiter keys."""
        while True:
            await asyncio.sleep(self.cleanup_interval_seconds)
            await self.cleanup_once()


rate_limiter = InMemoryRateLimiter(
    window_seconds=API_RATE_LIMIT_WINDOW_SECONDS,
    cleanup_interval_seconds=API_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
)

API_V1_PREFIX = "/api/v1"
LEGACY_API_PREFIX = "/api"
CSRF_PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
CSRF_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/register"}
CSRF_INVALID_MESSAGE = "CSRF token missing or invalid"


def _request_path(request: Request) -> str:
    """Read the current request path from the ASGI scope."""
    return request.scope.get("path", request.url.path)


def _to_legacy_api_path(path: str) -> str:
    """Map /api/v1/* requests onto existing /api/* routes."""
    if path == API_V1_PREFIX:
        return LEGACY_API_PREFIX
    if path.startswith(f"{API_V1_PREFIX}/"):
        return f"{LEGACY_API_PREFIX}/{path[len(API_V1_PREFIX) + 1:]}"
    return path


def _is_versioned_api_path(path: str) -> bool:
    """Return True for /api/v1 and /api/v1/* paths."""
    return path == API_V1_PREFIX or path.startswith(f"{API_V1_PREFIX}/")


def _is_legacy_api_path(path: str) -> bool:
    """Return True for /api and /api/* paths."""
    return path == LEGACY_API_PREFIX or path.startswith(f"{LEGACY_API_PREFIX}/")


def _ensure_request_id(request: Request) -> str:
    """Ensure request.state.request_id exists and return it."""
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    return request_id


def _is_rate_limit_exempt_path(path: str) -> bool:
    """Check if request path is exempt from API rate limiting."""
    path = _to_legacy_api_path(path)
    for exempt_path in API_RATE_LIMIT_EXEMPT_PATHS:
        if path == exempt_path or path.startswith(f"{exempt_path}/"):
            return True
    return False


def _is_csrf_exempt_path(path: str) -> bool:
    """Check if request path is exempt from CSRF validation."""
    normalized_path = (_to_legacy_api_path(path).rstrip("/") or "/")
    return normalized_path in CSRF_EXEMPT_PATHS


def _client_ip(request: Request) -> str:
    """Resolve client IP with proxy header support."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _metrics_endpoint_label(request: Request) -> str:
    """
    Build a stable endpoint label to avoid high-cardinality metrics.

    Prefer route templates like `/api/crawl/{crawl_id}/status` when available.
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and route_path:
            return _to_legacy_api_path(route_path)
    return _to_legacy_api_path(_request_path(request))


def _extract_authenticated_identity(request: Request) -> str | None:
    """
    Extract authenticated identity from JWT for per-user rate limiting.

    Uses explicit user id claims when present, and falls back to `sub`
    to remain compatible with existing tokens.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

    user_id = payload.get("user_id") or payload.get("uid")
    if user_id is not None:
        return str(user_id)

    subject = payload.get("sub")
    if subject is not None:
        return str(subject)

    return None


def _extract_authenticated_subject(request: Request) -> str | None:
    """Extract JWT subject for CSRF token binding when available."""
    auth_header = request.headers.get("authorization")
    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

    subject = payload.get("sub")
    return str(subject) if subject is not None else None

# ============================================================================
# LIFESPAN
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("PolicyCheck v6 starting")
    logger.info("=" * 60)

    validate_configuration()
    init_db()

    if not check_database_health():
        raise RuntimeError("Database health check failed after init")

    init_cache()

    # Clean up orphaned "running" crawls from previous sessions
    try:
        from app.database import SessionLocal
        from app.models import CrawlSession, Document
        from datetime import datetime, timezone
        from pathlib import Path as _Path
        cleanup_db = SessionLocal()
        try:
            stuck_crawls = cleanup_db.query(CrawlSession).filter(
                CrawlSession.status.in_(["running", "queued"])
            ).all()
            if stuck_crawls:
                for crawl in stuck_crawls:
                    old_status = crawl.status
                    crawl.status = "failed"
                    crawl.completed_at = datetime.now(timezone.utc)
                    logger.warning(f"Cleaned up stuck crawl #{crawl.id} (was '{old_status}' -> 'failed')")
                cleanup_db.commit()
                logger.info(f"Cleaned up {len(stuck_crawls)} orphaned crawl(s)")
            
            # Purge orphan document records (DB entries with missing files)
            all_docs = cleanup_db.query(Document).all()
            orphan_count = 0
            for doc in all_docs:
                if not doc.local_file_path or not _Path(doc.local_file_path).exists():
                    cleanup_db.delete(doc)
                    orphan_count += 1
            if orphan_count > 0:
                cleanup_db.commit()
                logger.warning(f"Purged {orphan_count} orphan document records (files missing from disk)")
        finally:
            cleanup_db.close()
    except Exception as e:
        logger.error(f"Error during startup cleanup: {e}", exc_info=True)

    rate_limit_cleanup_task = None
    if API_RATE_LIMIT_ENABLED:
        rate_limit_cleanup_task = asyncio.create_task(rate_limiter.cleanup_loop())
        logger.info(
            "API rate limiting enabled: auth=%s/min anonymous=%s/min window=%ss",
            API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE,
            API_RATE_LIMIT_ANONYMOUS_PER_MINUTE,
            API_RATE_LIMIT_WINDOW_SECONDS,
        )
    else:
        logger.warning("API rate limiting disabled")

    logger.info("Startup complete")
    yield

    logger.info("Shutting down...")
    if rate_limit_cleanup_task:
        rate_limit_cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await rate_limit_cleanup_task
    close_cache()
    dispose_engine()
    logger.info("Shutdown complete")


# ============================================================================
# APP
# ============================================================================

app = FastAPI(
    title="PolicyCheck v6",
    description="Policy document ingestion platform",
    version="6.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================================
# GLOBAL EXCEPTION HANDLER - Logs all errors to Docker
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch all unhandled exceptions and log them to Docker with full details.
    This ensures no error goes unnoticed in production.
    """
    request_id = _ensure_request_id(request)
    error_details = {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "request_id": request_id,
        "method": request.method,
        "url": str(request.url),
        "client_ip": _client_ip(request),
    }
    
    # Log with full traceback for debugging
    logger.error(
        "=" * 80 + "\n"
        "🚨 UNHANDLED EXCEPTION CAUGHT\n"
        "=" * 80 + "\n"
        f"Request ID: {request_id}\n"
        f"Error Type: {type(exc).__name__}\n"
        f"Error Message: {str(exc)}\n"
        f"Method: {request.method}\n"
        f"URL: {str(request.url)}\n"
        f"Client IP: {_client_ip(request)}\n"
        "=" * 80,
        exc_info=True  # This includes the full stack trace
    )
    
    # Return clean error to client
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred",
            "request_id": request_id,
            "error_type": type(exc).__name__ if not IS_PRODUCTION else "InternalServerError",
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Log HTTP exceptions (4xx, 5xx) to Docker for monitoring.
    """
    request_id = _ensure_request_id(request)
    
    # Log 5xx errors as ERROR, 4xx as WARNING
    log_level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
    
    logger.log(
        log_level,
        f"HTTP {exc.status_code} - {exc.detail} | "
        f"request_id={request_id} | "
        f"method={request.method} | "
        f"url={str(request.url)} | "
        f"client_ip={_client_ip(request)}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": request_id,
        }
    )

# ============================================================================
# CORS — allow all origins that are configured
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Collect request count/latency metrics when enabled."""
    if not METRICS_ENABLED:
        return await call_next(request)

    method = request.method
    endpoint = _metrics_endpoint_label(request)
    status_code = 500
    start = time.perf_counter()

    http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.perf_counter() - start
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code),
        ).inc()
        http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()


@app.middleware("http")
async def legacy_api_deprecation_middleware(request: Request, call_next):
    """Support /api/v1 routes and warn for legacy /api route usage."""
    path = _request_path(request)
    request_id = _ensure_request_id(request)

    if _is_versioned_api_path(path):
        request.state.original_path = path
        rewritten_path = _to_legacy_api_path(path)
        request.scope["path"] = rewritten_path
        request.scope["raw_path"] = rewritten_path.encode("utf-8")
    elif _is_legacy_api_path(path):
        logger.warning(
            "Legacy API route used request_id=%s path=%s migrate_to=%s",
            request_id,
            path,
            f"{API_V1_PREFIX}{path[len(LEGACY_API_PREFIX):]}",
        )

    return await call_next(request)


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """Validate CSRF header on state-changing requests."""
    path = _request_path(request)
    if request.method.upper() not in CSRF_PROTECTED_METHODS:
        return await call_next(request)

    if _is_csrf_exempt_path(path):
        return await call_next(request)

    csrf_token = request.headers.get("x-csrf-token")
    if not csrf_token:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": CSRF_INVALID_MESSAGE},
        )

    expected_subject = _extract_authenticated_subject(request)
    if not validate_csrf_token(csrf_token, expected_subject=expected_subject):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": CSRF_INVALID_MESSAGE},
        )

    return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate and propagate a request identifier for every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = _ensure_request_id(request)
        token = _request_id_ctx_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response


# Add after CSRF middleware, before rate limiting.
app.add_middleware(RequestIDMiddleware)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Log every HTTP request and response to Docker for monitoring and debugging.
    Skips health checks to reduce noise.
    """
    path = _request_path(request)
    
    # Skip logging for health checks to reduce noise
    if path in ["/health/liveness", "/health/readiness"]:
        return await call_next(request)
    
    request_id = _ensure_request_id(request)
    start_time = time.perf_counter()
    
    # Log incoming request
    logger.info(
        f"➡️  Incoming Request | "
        f"request_id={request_id} | "
        f"method={request.method} | "
        f"path={path} | "
        f"client_ip={_client_ip(request)}"
    )
    
    # Process request
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Log response with duration
        log_level = logging.ERROR if response.status_code >= 500 else logging.INFO
        logger.log(
            log_level,
            f"⬅️  Response | "
            f"request_id={request_id} | "
            f"status={response.status_code} | "
            f"duration={duration_ms:.2f}ms | "
            f"path={path}"
        )
        
        return response
        
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f"❌ Request Failed | "
            f"request_id={request_id} | "
            f"error={type(e).__name__}: {str(e)} | "
            f"duration={duration_ms:.2f}ms | "
            f"path={path}",
            exc_info=True
        )
        raise


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply per-user/IP API rate limits and return 429 with Retry-After."""
    path = _request_path(request)

    if not API_RATE_LIMIT_ENABLED:
        return await call_next(request)

    if _is_rate_limit_exempt_path(path):
        return await call_next(request)

    identity = _extract_authenticated_identity(request)
    if identity:
        rate_limit_key = f"user:{identity}"
        limit = API_RATE_LIMIT_AUTHENTICATED_PER_MINUTE
    else:
        rate_limit_key = f"ip:{_client_ip(request)}"
        limit = API_RATE_LIMIT_ANONYMOUS_PER_MINUTE

    allowed, retry_after = await rate_limiter.check_and_increment(rate_limit_key, limit)
    if not allowed:
        request_id = _ensure_request_id(request)
        logger.warning(
            "Rate limit exceeded request_id=%s key=%s method=%s path=%s retry_after=%s",
            request_id,
            rate_limit_key,
            request.method,
            path,
            retry_after,
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
            content={"detail": "Rate limit exceeded. Please retry later."},
        )

    return await call_next(request)


# ============================================================================
# ROUTERS
# ============================================================================

# Keep legacy /api routes active for backward compatibility.
app.include_router(auth_router.router)
app.include_router(crawl_router.router)
app.include_router(documents_router.router)
app.include_router(system_router.router)
app.include_router(stats_router.router)
app.include_router(audit_router.router)


def custom_openapi():
    """
    Expose versioned API paths in docs while keeping legacy aliases active.

    Runtime routing supports both /api/* (legacy) and /api/v1/* (preferred).
    Documentation shows only /api/v1/* for forward compatibility.
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=(
            f"{app.description}\n\n"
            "API versioning: use `/api/v1/*`. Legacy `/api/*` routes are still "
            "supported temporarily and emit deprecation warnings."
        ),
        routes=app.routes,
    )

    remapped_paths = {}
    for path, path_item in openapi_schema.get("paths", {}).items():
        if path.startswith(f"{LEGACY_API_PREFIX}/"):
            versioned_path = f"{API_V1_PREFIX}{path[len(LEGACY_API_PREFIX):]}"
            remapped_paths[versioned_path] = path_item
            continue
        remapped_paths[path] = path_item

    openapi_schema["paths"] = remapped_paths
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ============================================================================
# ROOT ENDPOINTS
# ============================================================================


@app.get("/")
def root():
    return {
        "service": "PolicyCheck v6",
        "version": "6.0.0",
        "status": "operational",
    }


@app.get("/health")
def health():
    """Comprehensive health check for operators."""
    if shutdown_event:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "shutting_down"},
        )
    try:
        db_healthy = check_database_health()
        cache_status = get_cache_status()
        storage_available = RAW_STORAGE_DIR.exists()
        cache_ready = bool(cache_status.get("connected", False))

        pool_stats = get_pool_status()
        active_crawls = crawl_service.get_active_crawl_count()
        all_ready = db_healthy and storage_available and (not CACHE_ENABLED or cache_ready)
        health_data = {
            "status": "healthy" if all_ready else "degraded",
            "version": "6.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": {
                "connected": db_healthy,
                "pool": pool_stats,
            },
            "cache": cache_status,
            "services": {
                "crawl": {
                    "active": active_crawls,
                    "capacity": crawl_service.MAX_CONCURRENT_CRAWLS,
                }
            },
            "storage": {
                "available": storage_available,
                "path": str(RAW_STORAGE_DIR),
            },
        }

        if all_ready:
            return health_data

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=health_data,
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


@app.get("/health/liveness")
def liveness():
    """Liveness probe - checks that process is alive and not shutting down."""
    if shutdown_event:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health/readiness")
def readiness():
    """Readiness probe - checks dependencies needed to serve traffic."""
    db_healthy = check_database_health()
    cache_status = get_cache_status()
    storage_available = RAW_STORAGE_DIR.exists()
    cache_ready = bool(cache_status.get("connected", False))

    checks = {
        "database": db_healthy,
        "cache": cache_ready if CACHE_ENABLED else True,
        "storage": storage_available,
    }
    ready = all(checks.values()) and not shutdown_event

    payload = {
        "ready": ready,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not ready:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/ready")
def legacy_readiness_alias():
    """Legacy readiness alias kept for backward compatibility."""
    return readiness()


@app.get("/metrics", include_in_schema=False)
def metrics():
    """Prometheus metrics endpoint."""
    if not METRICS_ENABLED:
        raise HTTPException(status_code=404, detail="Metrics are disabled")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# DEV SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
