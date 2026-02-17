"""
Production-hardened crawl service - Ingestion engine.

CRITICAL IMPROVEMENTS FROM V5:
1. Thread-safe robots.txt cache with locking
2. Concurrent crawl limit enforcement  
3. Better error handling with specific exceptions
4. Structured logging with crawl_id context
5. Improved duplicate detection before download
6. Memory-efficient operations with bounds checking
7. Graceful handling of time limits
8. Atomic file operations with better cleanup
9. Connection pool reuse across requests
10. BeautifulSoup parser explicitly specified

HANDLES:
- Crawl session creation with validation
- Real PDF discovery and download
- Keyword and policy type filtering
- File storage with deduplication
- Progress tracking
- Resource limits and safety
"""
import os
import re
import time
import hashlib
import logging
import tempfile
import threading
import urllib.robotparser
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse, urljoin, urlunparse, parse_qs, urlencode

import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from urllib3.util.timeout import Timeout
from urllib3.util.retry import Retry

from app.cache import invalidate_cache_prefix
from app.models import CrawlSession, Document, User
from app.config import (
    RAW_STORAGE_DIR, REQUEST_DELAY,
    CRAWL_CONNECT_TIMEOUT, CRAWL_READ_TIMEOUT, CRAWL_TOTAL_TIMEOUT,
    USER_AGENT, TRACKING_PARAMS, MAX_FILE_SIZE_BYTES,
    CHUNK_SIZE, MAX_DOWNLOAD_TIME, CRAWL_MAX_RETRIES,
    MAX_PAGES_ABSOLUTE, MAX_MINUTES_ABSOLUTE,
    MAX_CONCURRENT_CRAWLS, CRAWL_RESPECT_ROBOTS,
    CRAWL_MODE, CRAWL_PDF_CONCURRENCY
)

logger = logging.getLogger(__name__)

# ============================================================================
# THREAD-SAFE GLOBAL STATE
# ============================================================================

# Robots.txt cache with thread safety
_ROBOTS_CACHE: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
_ROBOTS_CACHE_LOCK = threading.Lock()

# Active crawl tracking for concurrency limits
_ACTIVE_CRAWLS: Dict[int, datetime] = {}  # crawl_id -> start_time
_ACTIVE_CRAWLS_LOCK = threading.Lock()

# In-memory crawl log store for live UI streaming
_CRAWL_LOGS: Dict[int, List[Dict[str, Any]]] = {}
_CRAWL_LOGS_LOCK = threading.Lock()
MAX_LOG_ENTRIES = 2000  # per crawl (increased for large crawls)


def crawl_log(crawl_id: int, level: str, message: str):
    """Add a log entry to the in-memory crawl log store."""
    with _CRAWL_LOGS_LOCK:
        if crawl_id not in _CRAWL_LOGS:
            _CRAWL_LOGS[crawl_id] = []
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "msg": message,
        }
        logs = _CRAWL_LOGS[crawl_id]
        logs.append(entry)
        # Trim old entries
        if len(logs) > MAX_LOG_ENTRIES:
            _CRAWL_LOGS[crawl_id] = logs[-MAX_LOG_ENTRIES:]


def get_crawl_logs(crawl_id: int, since: int = 0) -> List[Dict[str, Any]]:
    """Get log entries for a crawl, optionally since a given index."""
    with _CRAWL_LOGS_LOCK:
        logs = _CRAWL_LOGS.get(crawl_id, [])
        return logs[since:]


def clear_crawl_logs(crawl_id: int):
    """Clear logs for a completed crawl."""
    with _CRAWL_LOGS_LOCK:
        _CRAWL_LOGS.pop(crawl_id, None)


# ============================================================================
# CONCURRENCY MANAGEMENT (CRITICAL FIX #1)
# ============================================================================

def can_start_crawl() -> Tuple[bool, Optional[str]]:
    """
    Check if a new crawl can be started based on concurrency limits.
    
    Returns:
        (can_start, reason_if_not)
    
    CRITICAL FIX: Enforces MAX_CONCURRENT_CRAWLS to prevent resource exhaustion.
    """
    with _ACTIVE_CRAWLS_LOCK:
        active_count = len(_ACTIVE_CRAWLS)
        
        if active_count >= MAX_CONCURRENT_CRAWLS:
            oldest_crawl_id = min(_ACTIVE_CRAWLS.keys(), key=lambda k: _ACTIVE_CRAWLS[k])
            return False, (
                f"Maximum concurrent crawls ({MAX_CONCURRENT_CRAWLS}) reached. "
                f"Oldest active crawl: #{oldest_crawl_id}"
            )
        
        return True, None


def register_active_crawl(crawl_id: int) -> None:
    """Register a crawl as active."""
    with _ACTIVE_CRAWLS_LOCK:
        _ACTIVE_CRAWLS[crawl_id] = datetime.now(timezone.utc)
        logger.info(
            f"Registered active crawl {crawl_id} "
            f"({len(_ACTIVE_CRAWLS)}/{MAX_CONCURRENT_CRAWLS} slots used)"
        )


def unregister_active_crawl(crawl_id: int) -> None:
    """Unregister a crawl as active."""
    with _ACTIVE_CRAWLS_LOCK:
        if crawl_id in _ACTIVE_CRAWLS:
            del _ACTIVE_CRAWLS[crawl_id]
            logger.info(
                f"Unregistered active crawl {crawl_id} "
                f"({len(_ACTIVE_CRAWLS)}/{MAX_CONCURRENT_CRAWLS} slots used)"
            )


def get_active_crawl_count() -> int:
    """Get number of currently active crawls."""
    with _ACTIVE_CRAWLS_LOCK:
        return len(_ACTIVE_CRAWLS)


# ============================================================================
# HTTP SESSION FACTORY
# ============================================================================

def get_session_with_retries(verify_ssl: bool = True) -> requests.Session:
    """
    Create requests session with connection pooling and retry logic.
    
    OPTIMIZATION: Reuses connections, implements exponential backoff.
    FIX v7: Added SSL verification bypass for sites with bad/mismatched certs.
    """
    import urllib3
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    session = requests.Session()
    session.verify = verify_ssl
    
    # Retry configuration with exponential backoff
    retry_strategy = Retry(
        total=CRAWL_MAX_RETRIES,
        connect=CRAWL_MAX_RETRIES,
        read=CRAWL_MAX_RETRIES,
        status=CRAWL_MAX_RETRIES,
        backoff_factor=1,  # 1s, 2s, 4s delays
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        respect_retry_after_header=True,
        raise_on_status=False  # Let us handle status codes
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=20,
        pool_maxsize=40,
        pool_block=False  # Don't block waiting for connection
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({'User-Agent': USER_AGENT})
    
    return session


def build_request_timeout() -> Timeout:
    """
    Build per-request timeout configuration.

    NOTE: Timeout objects are stateful in urllib3, so create a fresh instance
    for each request.
    """
    return Timeout(
        connect=CRAWL_CONNECT_TIMEOUT,
        read=CRAWL_READ_TIMEOUT,
        total=CRAWL_TOTAL_TIMEOUT
    )


# ============================================================================
# ROBOTS.TXT HANDLING (THREAD-SAFE FIX #2)
# ============================================================================

def can_fetch(url: str, session: requests.Session) -> bool:
    """
    Check if URL can be fetched according to robots.txt.
    
    IMPROVEMENTS:
    - Thread-safe cache access with lock
    - Better error handling
    - Fail-open on robots.txt errors
    - Configurable bypass via CRAWL_RESPECT_ROBOTS
    """
    # BYPASS MODE - controlled via CRAWL_RESPECT_ROBOTS env var
    if not CRAWL_RESPECT_ROBOTS:
        logger.warning(f"⚠️ ROBOTS.TXT BYPASSED for {url} - Use responsibly")
        return True

    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        # Thread-safe cache check
        with _ROBOTS_CACHE_LOCK:
            if robots_url in _ROBOTS_CACHE:
                rp = _ROBOTS_CACHE[robots_url]
                if rp is None:
                    logger.debug(f"No robots.txt cached for {parsed.netloc}, allowing: {url}")
                    return True
                result = rp.can_fetch(USER_AGENT, url)
                logger.debug(f"Robots.txt check (cached) for {url}: {result}")
                return result
        
        # Cache miss - fetch robots.txt
        logger.info(f"Fetching robots.txt from {robots_url}")
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        
        try:
            rp.read()
            logger.info(f"✓ Successfully loaded robots.txt from {robots_url}")
            
            # Cache the parser
            with _ROBOTS_CACHE_LOCK:
                _ROBOTS_CACHE[robots_url] = rp
            
            result = rp.can_fetch(USER_AGENT, url)
            logger.info(f"Robots.txt decision for {url}: {'ALLOWED' if result else 'BLOCKED'}")
            return result
        except Exception as e:
            logger.info(f"✓ No robots.txt at {robots_url} (allowing crawl): {str(e)}")
            
            # Cache None to indicate no robots.txt
            with _ROBOTS_CACHE_LOCK:
                _ROBOTS_CACHE[robots_url] = None
            
            return True  # Allow crawling if robots.txt unavailable
    
    except Exception as e:
        logger.warning(f"Error checking robots.txt for {url}: {str(e)}")
        return True  # Fail-open on unexpected errors


# ============================================================================
# CRAWL SESSION CREATION
# ============================================================================

def create_crawl_session(
    db: Session,
    user: User,
    country: str,
    max_pages: int,
    max_minutes: int,
    seed_urls: List[str],
    policy_types: List[str],
    keyword_filters: List[str]
) -> CrawlSession:
    """
    Create a new crawl session with validation.
    
    IMPROVEMENTS:
    - Enforces hard limits on max_pages and max_minutes
    - Validates inputs
    - Better logging
    """
    # Enforce hard limits
    max_pages = min(max_pages, MAX_PAGES_ABSOLUTE)
    max_minutes = min(max_minutes, MAX_MINUTES_ABSOLUTE)
    
    # Validate inputs
    if not seed_urls:
        raise ValueError("At least one seed URL is required")
    
    if not keyword_filters:
        logger.warning("No keyword filters specified - will accept all PDFs")
    
    session = CrawlSession(
        user_id=user.id,
        country=country,
        max_pages=max_pages,
        max_minutes=max_minutes,
        seed_urls=seed_urls,
        policy_types=policy_types,
        keyword_filters=keyword_filters,
        status="queued",
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    logger.info(
        f"Created crawl session {session.id} for user {user.username} "
        f"(country={country}, max_pages={max_pages}, max_minutes={max_minutes}, "
        f"seeds={len(seed_urls)}, filters={len(keyword_filters)})"
    )
    
    return session


# ============================================================================
# DOCUMENT VALIDATION
# ============================================================================

def is_valid_document(
    url: str,
    keyword_filters: List[str],
    policy_types: List[str]
) -> Tuple[bool, Optional[str]]:
    """
    Check if URL matches keyword and policy type filters.
    
    Returns:
        (is_valid, matched_policy_type)
    
    IMPROVED: Accept ALL PDFs from the target domains. Classification
    happens after download. Keyword filters are used to boost priority
    but do not exclude.
    """
    url_lower = url.lower()
    
    # Always accept PDFs - we classify after download
    # But try to determine policy type for metadata
    
    # Policy type mapping
    policy_type_map = {
        "life": ["life", "lif", "living", "death", "tpd", "income protection", "trauma"],
        "home": ["home", "house", "property", "building", "landlord", "rental", "dwelling"],
        "contents": ["contents", "contents plus", "personal belongings", "valuables", "household contents"],
        "motor": ["motor", "vehicle", "car", "auto", "comprehensive", "third party", "tpft"],
        "travel": ["travel", "trip", "overseas", "holiday", "international"],
        "health": ["health", "medical", "hospital", "dental", "optical"],
        "business": ["business", "commercial", "liability", "sme", "professional indemnity", "public liability"],
        "pet": ["pet", "dog", "cat", "animal"],
        "marine": ["marine", "boat", "watercraft", "yacht"],
    }
    
    # Try to determine policy type from URL
    for policy_type in (policy_types or []):
        policy_keywords = policy_type_map.get(policy_type.lower(), [policy_type.lower()])
        if any(pk in url_lower for pk in policy_keywords):
            logger.debug(f"Accepted ({policy_type}): {url}")
            return True, policy_type
    
    # Check keyword filters for classification hints
    if keyword_filters:
        keyword_match = any(keyword.lower() in url_lower for keyword in keyword_filters)
        if keyword_match:
            logger.debug(f"Accepted (keyword match): {url}")
            return True, "General"
    
    # Accept all PDFs regardless - we classify after download
    if url_lower.endswith('.pdf') or url_lower.endswith('.pdf/'):
        logger.debug(f"Accepted (PDF file): {url}")
        return True, "General"
    
    logger.debug(f"Filtered out (not a PDF): {url}")
    return False, None

# ============================================================================
# URL NORMALIZATION & VALIDATION
# ============================================================================

def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    
    OPTIMIZATION: Remove tracking params, fragments, trailing slashes.
    """
    parsed = urlparse(url)
    
    # Normalize path
    path = parsed.path.rstrip('/') or '/'
    
    # Filter out tracking parameters
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        params = {
            k: v for k, v in params.items()
            if k.lower() not in TRACKING_PARAMS
        }
        query = urlencode(params, doseq=True) if params else ''
    else:
        query = ''
    
    # Normalize scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    
    return urlunparse((scheme, netloc, path, parsed.params, query, ''))


def is_pdf_url(url: str) -> bool:
    """Check if URL points to a PDF. Handles query params and fragments."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    # Direct .pdf extension
    if path.endswith('.pdf') or path.endswith('.pdf/'):
        return True
    # .pdf somewhere in path (e.g., /download/policy.pdf/view)
    if '.pdf' in path:
        return True
    # Check query string for pdf references (e.g., ?file=motor.pdf&v=2)
    query = parsed.query.lower()
    if '.pdf' in query:
        return True
    return False


def is_potential_document_url(url: str, link_text: str = "") -> bool:
    """
    Check if a URL might lead to a downloadable document even if it doesn't
    end in .pdf. Used to decide whether to try a HEAD request.
    """
    url_lower = url.lower()
    text_lower = link_text.lower() if link_text else ""

    doc_path_keywords = [
        '/download', '/document', '/getdocument', '/getfile',
        '/file/', '/media/', '/assets/', '/pdfs/', '/publications/',
        '/forms/', '/brochure', '/disclosure', '/resources/',
        '/policy-wording', '/policy-document', '/pds/',
        '/factsheet', '/fact-sheet', '/target-market',
        '/product-guide', '/claim-form', '/certificate',
        '/wp-content/uploads', '/sites/default/files',
    ]
    doc_text_keywords = [
        'download', 'pdf', 'policy wording', 'pds', 'fact sheet',
        'product disclosure', 'target market', 'brochure',
        'view document', 'open document', 'read more',
        'policy document', 'claim form', 'product guide',
        'view pdf', 'download pdf', 'full details',
        'terms and conditions', 'certificate of insurance',
        'supplementary', 'endorsement',
    ]

    if any(kw in url_lower for kw in doc_path_keywords):
        return True
    if any(kw in text_lower for kw in doc_text_keywords):
        return True
    return False


def check_url_is_pdf_via_head(url: str, session: requests.Session, crawl_id: int) -> bool:
    """
    Send a HEAD request to check if a URL serves a PDF via Content-Type.
    Used for URLs that might be PDFs but don't have .pdf extension.
    """
    try:
        resp = session.head(url, timeout=build_request_timeout(), allow_redirects=True)
        content_type = resp.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type:
            logger.info(f"[Crawl {crawl_id}] HEAD confirmed PDF: {url} (Content-Type: {content_type})")
            return True
        # Also check Content-Disposition header
        disposition = resp.headers.get('Content-Disposition', '').lower()
        if '.pdf' in disposition:
            logger.info(f"[Crawl {crawl_id}] HEAD confirmed PDF via disposition: {url}")
            return True
    except Exception as e:
        logger.debug(f"[Crawl {crawl_id}] HEAD request failed for {url}: {e}")
    return False


def same_domain(seed_url: str, candidate_url: str) -> bool:
    """
    Check if URLs are on same domain (allowing subdomains).
    
    CRITICAL FIX: Properly handles country-code TLDs like .co.nz, .com.au, .co.uk.
    Previous bug: get_base_domain('tower.co.nz') returned 'co.nz' which matched
    ALL .co.nz domains (smithandsmith.co.nz, canstar.co.nz, airnewzealand.co.nz).
    
    Now correctly returns 'tower.co.nz' for tower.co.nz domains.
    """
    # Known two-part country-code TLD suffixes
    CCLD_SUFFIXES = {
        'co.nz', 'org.nz', 'net.nz', 'govt.nz', 'ac.nz',
        'com.au', 'org.au', 'net.au', 'edu.au', 'gov.au',
        'co.uk', 'org.uk', 'me.uk', 'net.uk', 'gov.uk',
        'co.za', 'org.za', 'co.in', 'com.sg', 'com.hk', 'co.jp',
        'com.br', 'co.kr', 'com.mx', 'co.id',
    }
    
    def get_base_domain(netloc: str) -> str:
        """Extract base domain from netloc, handling ccTLDs."""
        netloc = netloc.lower().removeprefix('www.').split(':')[0]  # Remove port too
        parts = netloc.split('.')
        
        if len(parts) >= 3:
            # Check if last 2 parts form a known ccTLD suffix
            suffix = '.'.join(parts[-2:])
            if suffix in CCLD_SUFFIXES:
                # Return last 3 parts: e.g., 'tower.co.nz'
                return '.'.join(parts[-3:])
        
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return netloc
    
    seed_domain = get_base_domain(urlparse(seed_url).netloc)
    candidate_domain = get_base_domain(urlparse(candidate_url).netloc)
    
    return seed_domain == candidate_domain


# ============================================================================
# FILE HANDLING UTILITIES
# ============================================================================

def sanitize_filename(name: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    SECURITY: Removes dangerous characters and prevents directory traversal.
    """
    # Remove path separators and dangerous sequences
    safe_name = name.replace('/', '_').replace('\\', '_').replace('..', '_')
    
    # Allow only alphanumeric, underscore, hyphen, period
    safe_name = ''.join(c for c in safe_name if c.isalnum() or c in ('_', '-', '.'))
    
    # Ensure not empty and doesn't start with dot
    safe_name = safe_name.lstrip('.') or "unknown"
    
    # Limit length to prevent filesystem issues
    if len(safe_name) > 200:
        safe_name = safe_name[:200]
    
    return safe_name


def extract_insurer_name(url: str) -> str:
    """Extract and sanitize insurer name from URL."""
    domain = urlparse(url).netloc
    domain = domain.replace('www.', '')
    parts = domain.split('.')
    raw_name = parts[0].title() if parts else "Unknown"
    return sanitize_filename(raw_name)


def verify_path_safety(file_path: Path, allowed_parent: Path) -> bool:
    """
    Verify that file_path is safely within allowed_parent directory.
    
    SECURITY FIX: Prevents path traversal via symlinks.
    
    Returns:
        True if path is safe, False otherwise
    """
    try:
        # Resolve to absolute path (follows symlinks)
        resolved_path = file_path.resolve()
        resolved_parent = allowed_parent.resolve()
        
        # Check if resolved path is under parent
        return str(resolved_path).startswith(str(resolved_parent))
    except Exception as e:
        logger.error(f"Error verifying path safety: {e}")
        return False


# ============================================================================
# PDF DOWNLOAD WITH STREAMING
# ============================================================================

def download_pdf_streaming(
    url: str,
    save_path: Path,
    session: requests.Session,
    crawl_id: int
) -> Optional[Dict[str, Any]]:
    """
    Download PDF with streaming and concurrent hashing.
    
    CRITICAL OPTIMIZATIONS:
    - Streams download (doesn't load entire file in memory)
    - Computes hash during download (not after)
    - Enforces file size limit
    - Uses atomic write (temp file then move)
    - Validates content type
    - Has timeout protection
    - Better error handling and logging
    
    Returns:
        Dictionary with file_size and file_hash, or None if failed
    """
    temp_path = None
    
    try:
        logger.debug(f"[Crawl {crawl_id}] Downloading PDF: {url}")
        
        # SECURITY: Verify save path is safe
        if not verify_path_safety(save_path, RAW_STORAGE_DIR):
            logger.error(
                f"[Crawl {crawl_id}] Path traversal attempt detected: {save_path}"
            )
            return None
        
        response = session.get(
            url,
            timeout=build_request_timeout(),
            stream=True  # CRITICAL: Stream to avoid memory issues
        )
        
        if response.status_code != 200:
            logger.warning(
                f"[Crawl {crawl_id}] Failed to download {url}: "
                f"HTTP {response.status_code}"
            )
            return None
        
        # Validate content type
        content_type = response.headers.get('Content-Type', '').lower()
        content_disp = response.headers.get('Content-Disposition', '').lower()
        url_has_pdf = '.pdf' in url.lower()
        is_pdf_content = 'application/pdf' in content_type
        is_octet = 'application/octet-stream' in content_type
        disp_has_pdf = '.pdf' in content_disp
        
        if not is_pdf_content and not url_has_pdf and not disp_has_pdf and not is_octet:
            logger.warning(
                f"[Crawl {crawl_id}] URL {url} does not appear to be a PDF "
                f"(Content-Type: {content_type})"
            )
            return None
        
        # Check content length if provided
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > MAX_FILE_SIZE_BYTES:
            logger.warning(
                f"[Crawl {crawl_id}] PDF too large: {url} "
                f"({int(content_length) / 1024 / 1024:.2f}MB > "
                f"{MAX_FILE_SIZE_BYTES / 1024 / 1024}MB)"
            )
            return None
        
        # Ensure directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # CRITICAL: Write to temp file first (atomic operation)
        with tempfile.NamedTemporaryFile(
            mode='wb',
            dir=save_path.parent,
            delete=False,
            suffix='.tmp'
        ) as temp_file:
            temp_path = Path(temp_file.name)
            
            # OPTIMIZATION: Stream download and compute hash simultaneously
            sha256_hash = hashlib.sha256()
            bytes_downloaded = 0
            start_time = time.time()
            
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    # Check size limit
                    bytes_downloaded += len(chunk)
                    if bytes_downloaded > MAX_FILE_SIZE_BYTES:
                        logger.warning(
                            f"[Crawl {crawl_id}] PDF exceeded size limit during download: {url} "
                            f"({bytes_downloaded / 1024 / 1024:.2f}MB)"
                        )
                        temp_path.unlink()
                        return None
                    
                    # Check time limit
                    elapsed = time.time() - start_time
                    if elapsed > MAX_DOWNLOAD_TIME:
                        logger.warning(
                            f"[Crawl {crawl_id}] Download timeout for {url} "
                            f"({elapsed:.1f}s > {MAX_DOWNLOAD_TIME}s)"
                        )
                        temp_path.unlink()
                        return None
                    
                    temp_file.write(chunk)
                    sha256_hash.update(chunk)
            
            file_size = bytes_downloaded
            file_hash = sha256_hash.hexdigest()
        
        # ATOMIC: Move temp file to final location
        temp_path.replace(save_path)
        
        logger.info(
            f"[Crawl {crawl_id}] Downloaded PDF: {url} -> {save_path} "
            f"({file_size / 1024:.2f}KB, hash={file_hash[:8]}...)"
        )
        
        return {
            'file_size': file_size,
            'file_hash': file_hash
        }
    
    except requests.exceptions.Timeout:
        logger.error(f"[Crawl {crawl_id}] Timeout downloading {url}")
        if temp_path and temp_path.exists():
            temp_path.unlink()
        return None
    
    except requests.exceptions.RequestException as e:
        logger.error(f"[Crawl {crawl_id}] Request error downloading {url}: {e}")
        if temp_path and temp_path.exists():
            temp_path.unlink()
        return None
    
    except Exception as e:
        logger.error(
            f"[Crawl {crawl_id}] Unexpected error downloading {url}: {e}",
            exc_info=True
        )
        if temp_path and temp_path.exists():
            temp_path.unlink()
        return None


# ============================================================================
# SITEMAP EXTRACTION
# ============================================================================

def extract_from_sitemap(
    base_url: str,
    session: requests.Session,
    crawl_id: int
) -> Set[str]:
    """
    Try to extract PDF URLs from sitemap.xml.
    Much faster than crawling when available.
    """
    pdf_urls: Set[str] = set()
    
    sitemap_paths = [
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemaps/sitemap.xml",
        "/sitemap/sitemap.xml",
    ]
    
    for sitemap_path in sitemap_paths:
        sitemap_url = base_url.rstrip("/") + sitemap_path
        try:
            resp = session.get(sitemap_url, timeout=build_request_timeout())
            if resp.status_code == 200 and 'xml' in resp.headers.get('Content-Type', '').lower():
                # Parse XML
                root = ET.fromstring(resp.content)
                
                # Find all <loc> tags
                namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                locs = root.findall('.//ns:loc', namespaces) or root.findall('.//loc')
                
                for loc in locs:
                    url = loc.text
                    if url and '.pdf' in url.lower():
                        normalized = normalize_url(url)
                        pdf_urls.add(normalized)
                
                if pdf_urls:
                    logger.info(
                        f"[Crawl {crawl_id}] Found {len(pdf_urls)} PDFs in sitemap: {sitemap_url}"
                    )
                    return pdf_urls  # Return on first successful sitemap
        
        except Exception as e:
            logger.debug(f"[Crawl {crawl_id}] Failed to fetch sitemap {sitemap_url}: {e}")
            continue
    
    logger.info(f"[Crawl {crawl_id}] No sitemaps found or no PDFs in sitemaps")
    return pdf_urls


# ============================================================================
# DOMAIN CRAWLING ENGINE
# ============================================================================

def crawl_domain(
    seed_url: str,
    max_pages: int,
    keyword_filters: List[str],
    policy_types: List[str],
    session: requests.Session,
    crawl_id: int,
    time_limit: Optional[datetime] = None,
    global_visited: Optional[Set[str]] = None,
) -> Tuple[List[str], int]:
    """
    Crawl a domain to find PDF URLs with time and page limits.
    
    Args:
        global_visited: Shared visited set across seeds to skip already-crawled URLs.
    
    Returns:
        Tuple of (valid PDF URLs, actual pages crawled count)
    """
    # Handle direct PDF URLs
    if is_pdf_url(seed_url):
        normalized = normalize_url(seed_url)
        is_valid, _ = is_valid_document(normalized, keyword_filters, policy_types)
        if is_valid:
            logger.info(f'[Crawl {crawl_id}] Direct PDF seed: {normalized}')
            return [normalized], 1
        return [], 1
    
    # NEW: Try sitemap first - much faster!
    base_url = f"{urlparse(seed_url).scheme}://{urlparse(seed_url).netloc}"
    sitemap_pdfs = extract_from_sitemap(base_url, session, crawl_id)
    
    if sitemap_pdfs:
        logger.info(
            f'[Crawl {crawl_id}] Found {len(sitemap_pdfs)} PDFs via sitemap - '
            f'filtering now'
        )
        # Filter the PDFs
        valid_pdfs = []
        for pdf_url in sitemap_pdfs:
            is_valid, _ = is_valid_document(pdf_url, keyword_filters, policy_types)
            if is_valid:
                valid_pdfs.append(pdf_url)
        
        logger.info(
            f'[Crawl {crawl_id}] {len(valid_pdfs)}/{len(sitemap_pdfs)} PDFs passed filters'
        )
        if valid_pdfs:
            return valid_pdfs, 1  # Only 1 page "crawled"
    
    # Continue with regular crawl if no sitemap or no valid PDFs from sitemap
    domain = urlparse(seed_url).netloc
    logger.info(
        f'[Crawl {crawl_id}] Crawling domain: {domain} '
        f'(max_pages={max_pages}, time_limit={time_limit}, mode={CRAWL_MODE})'
    )
    
    pdf_urls: Set[str] = set()
    visited: Set[str] = global_visited if global_visited is not None else set()
    
    # Use deque for BFS or list for DFS based on CRAWL_MODE
    if CRAWL_MODE == "breadth":
        queue = deque([seed_url])
        logger.info(f'[Crawl {crawl_id}] Using breadth-first search')
    else:
        queue = deque([seed_url])  # Use deque for both for consistency
        logger.info(f'[Crawl {crawl_id}] Using depth-first search')
    
    pages_crawled = 0
    path_diversity = defaultdict(int)  # Track which paths we've explored
    
    while queue and pages_crawled < max_pages:
        # CRITICAL: Check time limit
        if time_limit and datetime.now(timezone.utc) > time_limit:
            logger.warning(
                f"[Crawl {crawl_id}] Time limit reached "
                f"(pages_crawled={pages_crawled}, pdfs_found={len(pdf_urls)})"
            )
            break
        
        # MEMORY: Limit visited set size to prevent memory exhaustion
        if len(visited) > max(max_pages * 5, 100000):
            logger.warning(
                f"[Crawl {crawl_id}] Visited set too large ({len(visited)}), "
                f"stopping crawl to prevent memory exhaustion"
            )
            break
        
        # BFS: popleft (FIFO), DFS: pop (LIFO)
        if CRAWL_MODE == "depth":
            url = queue.pop()
        else:
            url = queue.popleft()
        logger.info(f"[Crawl {crawl_id}] Processing URL from queue: {url} (queue_size={len(queue)}, visited={len(visited)})")
        
        if url in visited:
            logger.debug(f"[Crawl {crawl_id}] Already visited, skipping: {url}")
            continue
        
        # SECURITY: Check robots.txt
        can_fetch_result = can_fetch(url, session)
        logger.info(f"[Crawl {crawl_id}] Robots.txt check for {url}: {can_fetch_result}")
        if not can_fetch_result:
            logger.warning(f"[Crawl {crawl_id}] BLOCKED by robots.txt: {url}")
            visited.add(url)
            continue
        
        visited.add(url)
        
        # Stay on same domain
        if not same_domain(seed_url, url):
            logger.debug(f"[Crawl {crawl_id}] Skipping different domain: {url}")
            continue
        
        # Rate limiting
        if pages_crawled > 0:
            time.sleep(REQUEST_DELAY)
        
        pages_crawled += 1
        logger.info(f'[Crawl {crawl_id}] Fetching page {pages_crawled}/{max_pages}: {url}')
        
        try:
            resp = session.get(url, timeout=build_request_timeout())
            logger.info(f'[Crawl {crawl_id}] HTTP {resp.status_code} for {url}')
            
            if resp.status_code != 200:
                logger.warning(
                    f'[Crawl {crawl_id}] Non-200 status HTTP {resp.status_code}: {url}'
                )
                continue
            
            # Only parse HTML content
            content_type = resp.headers.get('Content-Type', '').lower()
            logger.info(f'[Crawl {crawl_id}] Content-Type: {content_type} for {url}')
            if 'text/html' not in content_type:
                logger.warning(
                    f'[Crawl {crawl_id}] Skipping non-HTML content: {url} '
                    f'(Content-Type: {content_type})'
                )
                continue
            
            # IMPROVEMENT: Explicitly specify parser for security
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Extract all links
            links_found = soup.find_all('a', href=True)
            logger.info(f'[Crawl {crawl_id}] Found {len(links_found)} links on {url}')
            
            links_added = 0
            pdfs_found_on_page = 0
            head_checked = 0
            MAX_HEAD_CHECKS_PER_PAGE = 25  # Increased for better PDF discovery
            
            for link in links_found:
                href = link['href'].strip()
                if not href or href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                    continue
                
                # Convert relative URLs to absolute
                full_url = urljoin(url, href)
                
                # Get link text for classification hints
                link_text = link.get_text(strip=True) or ""
                
                # Check if it's a PDF (by URL pattern)
                if is_pdf_url(full_url):
                    normalized = normalize_url(full_url)
                    is_valid, reason = is_valid_document(
                        normalized, keyword_filters, policy_types
                    )
                    
                    if is_valid and normalized not in pdf_urls:
                        pdf_urls.add(normalized)
                        pdfs_found_on_page += 1
                        
                        # CELEBRATE FIRST PDF!
                        if len(pdf_urls) == 1:
                            logger.info(
                                f'[Crawl {crawl_id}] 🎉🎉🎉 FIRST PDF FOUND! 🎉🎉🎉\n'
                                f'  URL: {normalized}\n'
                                f'  After {pages_crawled} pages crawled\n'
                                f'=========================================='
                            )
                        else:
                            logger.info(
                                f'[Crawl {crawl_id}] ✓ PDF #{len(pdf_urls)} found: '
                                f'{normalized}'
                            )
                    elif not is_valid:
                        logger.debug(
                            f'[Crawl {crawl_id}] ✗ Filtered PDF ({reason}): {normalized}'
                        )
                    continue
                
                # Check if URL/link text suggests a document download
                # Use HEAD request to verify (limited per page to avoid slowdown)
                if (head_checked < MAX_HEAD_CHECKS_PER_PAGE
                        and same_domain(seed_url, full_url)
                        and full_url not in visited
                        and full_url not in pdf_urls
                        and is_potential_document_url(full_url, link_text)):
                    head_checked += 1
                    if check_url_is_pdf_via_head(full_url, session, crawl_id):
                        normalized = normalize_url(full_url)
                        if normalized not in pdf_urls:
                            pdf_urls.add(normalized)
                            pdfs_found_on_page += 1
                            logger.info(
                                f'[Crawl {crawl_id}] ✓ PDF #{len(pdf_urls)} found via HEAD: '
                                f'{normalized} (link text: "{link_text[:60]}")'
                            )
                        continue
                
                # Add to queue if same domain and not visited
                if same_domain(seed_url, full_url) and full_url not in visited:
                    # Track path diversity
                    url_path = urlparse(full_url).path
                    path_prefix = "/".join(url_path.split("/")[:3])  # e.g., /documents/home
                    
                    # Limit how deep we go into each path to encourage diversity
                    if path_diversity[path_prefix] < 20:  # Max 20 pages per path prefix
                        # Prevent queue explosion
                        if len(queue) < max(max_pages * 5, 50000):
                            # OPTIMIZATION: Prioritize URLs likely to contain PDFs
                            pdf_keywords = ['document', 'form', 'download', 'pdf', 'policy', 
                                           'wording', 'pds', 'disclosure', 'legal', 'terms',
                                           'resources', 'publications', 'brochure', 'guide',
                                           'factsheet', 'fact-sheet', 'claim', 'certificate',
                                           'target-market', 'product-guide', 'media', 'assets',
                                           'uploads', 'files']
                            url_lower = full_url.lower()
                            is_priority = any(keyword in url_lower for keyword in pdf_keywords)
                            
                            # Boost diversity - prioritize unexplored path prefixes
                            is_diverse = path_diversity[path_prefix] < 5
                            
                            if is_priority or is_diverse:
                                # Insert near front of queue (after first 10 items to maintain some breadth)
                                insert_pos = min(10, len(queue))
                                queue.insert(insert_pos, full_url)
                                logger.debug(f"[Crawl {crawl_id}] ⭐ Priority URL queued: {full_url}")
                            else:
                                queue.append(full_url)
                            
                            path_diversity[path_prefix] += 1
                            links_added += 1
                        else:
                            logger.debug(
                                f"[Crawl {crawl_id}] Queue size limit reached "
                                f"({len(queue)}), not adding more URLs"
                            )
                    else:
                        logger.debug(
                            f"[Crawl {crawl_id}] Path diversity limit reached for {path_prefix}, "
                            f"skipping similar URL"
                        )
            
            # Also scan for embedded PDFs in iframes, objects, embeds
            for tag_name, attr in [('iframe', 'src'), ('embed', 'src'), ('object', 'data')]:
                for tag in soup.find_all(tag_name, attrs={attr: True}):
                    embed_url = urljoin(url, tag[attr].strip())
                    if is_pdf_url(embed_url):
                        normalized = normalize_url(embed_url)
                        if normalized not in pdf_urls:
                            pdf_urls.add(normalized)
                            pdfs_found_on_page += 1
                            logger.info(
                                f'[Crawl {crawl_id}] ✓ PDF #{len(pdf_urls)} '
                                f'found in <{tag_name}>: {normalized}'
                            )
            
            # Scan data-href, data-url, data-file attributes on any element
            for data_attr in ['data-href', 'data-url', 'data-file', 'data-src', 'data-pdf']:
                for tag in soup.find_all(attrs={data_attr: True}):
                    data_url = urljoin(url, tag[data_attr].strip())
                    if is_pdf_url(data_url):
                        normalized = normalize_url(data_url)
                        if normalized not in pdf_urls:
                            pdf_urls.add(normalized)
                            pdfs_found_on_page += 1
                            logger.info(
                                f'[Crawl {crawl_id}] ✓ PDF #{len(pdf_urls)} '
                                f'found in {data_attr}: {normalized}'
                            )
            
            # Scan for PDF links in onclick/href javascript patterns
            for tag in soup.find_all(attrs={'onclick': True}):
                onclick_val = tag.get('onclick', '')
                pdf_matches = re.findall(r"['\"]([^'\"]*\.pdf[^'\"]*)['\"]", onclick_val, re.IGNORECASE)
                for match in pdf_matches:
                    match_url = urljoin(url, match)
                    normalized = normalize_url(match_url)
                    if normalized not in pdf_urls and same_domain(seed_url, match_url):
                        pdf_urls.add(normalized)
                        pdfs_found_on_page += 1
                        logger.info(
                            f'[Crawl {crawl_id}] ✓ PDF #{len(pdf_urls)} '
                            f'found in onclick: {normalized}'
                        )
            
            logger.info(
                f'[Crawl {crawl_id}] Page processed: {pdfs_found_on_page} PDFs found, '
                f'{links_added} new URLs queued (queue_size={len(queue)})'
            )
            
            # PERIODIC STATUS REPORT: Every 20 pages
            if pages_crawled > 0 and pages_crawled % 20 == 0:
                logger.info(
                    f'[Crawl {crawl_id}] ========== PROGRESS REPORT ==========\n'
                    f'  Pages crawled: {pages_crawled}/{max_pages}\n'
                    f'  PDFs discovered: {len(pdf_urls)}\n'
                    f'  Queue size: {len(queue)} URLs pending\n'
                    f'  URLs visited: {len(visited)}\n'
                    f'=========================================='
                )
        
        except requests.exceptions.Timeout as e:
            logger.warning(f'[Crawl {crawl_id}] TIMEOUT fetching {url}: {str(e)}')
        
        except requests.exceptions.RequestException as e:
            logger.warning(f'[Crawl {crawl_id}] REQUEST ERROR fetching {url}: {str(e)}', exc_info=False)
        
        except Exception as e:
            logger.error(
                f'[Crawl {crawl_id}] UNEXPECTED ERROR parsing {url}: {str(e)}',
                exc_info=True
            )
    
    logger.info(
        f'[Crawl {crawl_id}] ========== CRAWL COMPLETE ==========\n'
        f'  Pages scanned: {pages_crawled}\n'
        f'  URLs visited: {len(visited)}\n'
        f'  URLs in final queue: {len(queue)}\n'
        f'  Valid PDFs found: {len(pdf_urls)}\n'
        f'=========================================='
    )
    
    return list(pdf_urls), pages_crawled


# ============================================================================
# PDF CLASSIFICATION & METADATA EXTRACTION
# ============================================================================

# Classification keywords mapped to document types
CLASSIFICATION_RULES = {
    "PDS": {
        "keywords": [
            "pds", "product disclosure", "product-disclosure", "productdisclosure",
            "combined fsg", "financial services guide",
        ],
        "weight": 1.0,
    },
    "Policy Wording": {
        "keywords": [
            "policy wording", "policy-wording", "policywording", "wording",
            "policy document", "policy schedule", "terms and conditions",
            "conditions of cover", "cover wording",
        ],
        "weight": 0.9,
    },
    "Fact Sheet": {
        "keywords": [
            "fact sheet", "fact-sheet", "factsheet", "key facts", "keyfacts",
            "key information", "summary of cover", "cover summary",
        ],
        "weight": 0.85,
    },
    "TMD": {
        "keywords": [
            "tmd", "target market", "target-market", "targetmarket",
            "target market determination",
        ],
        "weight": 0.9,
    },
    "Product Guide": {
        "keywords": [
            "product guide", "product-guide", "productguide", "guide",
            "brochure", "overview",
        ],
        "weight": 0.7,
    },
    "Certificate of Insurance": {
        "keywords": [
            "certificate of insurance", "certificate-of-insurance",
            "coi", "proof of insurance",
        ],
        "weight": 0.85,
    },
    "Claim Form": {
        "keywords": [
            "claim form", "claim-form", "claimform", "claims form",
            "make a claim", "lodge a claim",
        ],
        "weight": 0.8,
    },
}

# Policy type (category) detection rules
POLICY_TYPE_RULES = {
    "Motor": [
        "motor", "vehicle", "car", "auto", "comprehensive",
        "third party", "tpft", "third-party", "automotive",
    ],
    "Home": [
        "home", "house", "property", "building", "dwelling",
        "homeowner", "home-owner", "residential",
    ],
    "Contents": [
        "contents", "contents plus", "contents-plus", "personal belongings",
        "household contents", "valuables",
    ],
    "Landlord": [
        "landlord", "rental", "rental property", "investment property",
        "landlords",
    ],
    "Travel": [
        "travel", "trip", "overseas", "holiday", "international",
    ],
    "Life": [
        "life", "lif", "living", "death", "tpd",
        "income protection", "trauma", "funeral",
    ],
    "Health": [
        "health", "medical", "hospital", "dental", "optical",
        "surgical", "wellness",
    ],
    "Business": [
        "business", "commercial", "liability", "sme",
        "professional indemnity", "public liability", "trade",
    ],
    "Pet": [
        "pet", "dog", "cat", "animal", "puppy", "kitten",
        "pet insurance", "pet-insurance", "petinsurance",
        "veterinary", "veterinarian", "vet cover", "vet care",
        "vet insurance", "companion animal", "canine", "feline",
        "breed", "pedigree", "pet health", "pet care", "pet plan",
        "animal cover", "pet policy", "fur baby", "dog insurance",
        "cat insurance", "pet protection", "vet bill", "vet fees",
        "pet medical", "pet accident", "pet illness",
    ],
    "Marine": [
        "marine", "boat", "watercraft", "yacht", "vessel",
    ],
}

# Insurer name patterns for better extraction
KNOWN_INSURERS = {
    "aainsurance": "AA Insurance",
    "aa-insurance": "AA Insurance",
    "ami": "AMI Insurance",
    "tower": "Tower Insurance",
    "state": "State Insurance",
    "aia": "AIA New Zealand",
    "southern-cross": "Southern Cross",
    "southerncross": "Southern Cross",
    "partners-life": "Partners Life",
    "partnerslife": "Partners Life",
    "nib": "nib Insurance",
    "fidelity": "Fidelity Life",
    "cigna": "Cigna Insurance",
    "asteron": "Asteron Life",
    "suncorp": "Suncorp",
    "iag": "IAG",
    "vero": "Vero Insurance",
    "chubb": "Chubb Insurance",
    "allianz": "Allianz",
    "zurich": "Zurich Insurance",
    "qbe": "QBE Insurance",
    "tmi": "TMI (The Mutual Insurance)",
    "initio": "Initio Insurance",
    "ando": "Ando Insurance",
    "youi": "Youi Insurance",
    "trade-me": "Trade Me Insurance",
    "trademe": "Trade Me Insurance",
    "pinnacle": "Pinnacle Life",
    "accuro": "Accuro Health Insurance",
}


def classify_document(
    url: str,
    filename: str,
    policy_type: str,
    file_size: Optional[int] = None,
    pdf_text_sample: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Classify a downloaded PDF based on URL, filename, and optional text content.
    
    Returns:
        Dict with classification, confidence, detected_policy_type, warnings, metadata
    
    Pipeline stages:
    1. URL-based classification (check URL path)
    2. Filename-based classification (check filename)
    3. Text-based classification (check first pages if available)
    4. Policy type auto-detection (motor, home, contents, etc.)
    5. Confidence scoring
    6. Auto-approve/needs-review decision
    """
    url_lower = url.lower()
    filename_lower = filename.lower()
    combined = f"{url_lower} {filename_lower}"
    if pdf_text_sample:
        combined += f" {pdf_text_sample.lower()}"
    
    classification = "Unclassified"
    confidence = 0.0
    warnings: List[str] = []
    matched_source = ""
    
    # Stage 1 & 2: URL + filename classification (document type)
    best_match_score = 0.0
    for doc_type, rules in CLASSIFICATION_RULES.items():
        for keyword in rules["keywords"]:
            if keyword in combined:
                score = rules["weight"]
                # Boost if matched in URL path (more reliable)
                if keyword in url_lower:
                    score += 0.05
                # Boost if matched in filename
                if keyword in filename_lower:
                    score += 0.05
                # Boost if found in text content
                if pdf_text_sample and keyword in pdf_text_sample.lower():
                    score += 0.1
                
                if score > best_match_score:
                    best_match_score = score
                    classification = doc_type
                    matched_source = f"matched '{keyword}'"
    
    # Stage 3: Policy type auto-detection
    detected_policy_type = policy_type  # fallback to provided
    best_pt_score = 0
    for pt_name, pt_keywords in POLICY_TYPE_RULES.items():
        score = 0
        for kw in pt_keywords:
            # Higher weight for multi-word exact matches (e.g., "pet insurance")
            kw_is_multiword = " " in kw or "-" in kw
            
            if kw in url_lower:
                score += 4 if kw_is_multiword else 2
            if kw in filename_lower:
                score += 6 if kw_is_multiword else 3
            if pdf_text_sample and kw in pdf_text_sample.lower():
                score += 3 if kw_is_multiword else 1
        
        # Special boost for Pet to compensate for previous under-detection
        if pt_name == "Pet" and score > 0:
            score = int(score * 1.2)
        
        if score > best_pt_score:
            best_pt_score = score
            detected_policy_type = pt_name
    
    # If we detected a policy type, boost confidence
    if best_pt_score > 0 and best_match_score > 0:
        best_match_score = min(best_match_score + 0.05, 1.0)
    
    # Calculate confidence
    if best_match_score > 0:
        confidence = min(best_match_score, 1.0)
    elif best_pt_score > 0:
        # No doc type keyword matched but we identified a policy category
        # This is still useful - set as General Document with moderate confidence
        confidence = min(0.4 + (best_pt_score * 0.05), 0.7)
        classification = "General Document"
        warnings.append("Document type unclear — policy category detected from filename/text")
    else:
        # No keyword match at all — try to infer from general context
        if ".pdf" in url_lower or ".pdf" in filename_lower:
            confidence = 0.3
            classification = "General Document"
            warnings.append("No classification keyword match")
        else:
            confidence = 0.1
            classification = "Unknown"
            warnings.append("Unable to classify")
    
    # Adjust confidence based on file size heuristics
    if file_size:
        if file_size < 10_000:  # Less than 10KB — probably not a real policy doc
            confidence *= 0.5
            warnings.append("Very small file")
        elif file_size < 50_000:  # Less than 50KB
            confidence *= 0.8
            warnings.append("Small file size")
        elif file_size > 20_000_000:  # More than 20MB
            confidence *= 0.9
            warnings.append("Very large file")
    
    # Determine status based on confidence
    if confidence >= 0.85:
        status = "auto-approved"
    elif confidence >= 0.5:
        status = "needs-review"
        if "Low confidence" not in [w for w in warnings]:
            warnings.append("Low confidence — manual review recommended")
    else:
        status = "needs-review"
        warnings.append("Very low confidence — requires manual review")
    
    # Extract better insurer name
    insurer_name = None
    domain = urlparse(url).netloc.lower().replace("www.", "")
    domain_base = domain.split(".")[0] if domain else ""
    for pattern, name in KNOWN_INSURERS.items():
        if pattern in domain_base or pattern in domain:
            insurer_name = name
            break
    
    return {
        "classification": classification,
        "confidence": round(confidence, 2),
        "status": status,
        "warnings": warnings,
        "insurer_name": insurer_name,
        "matched_source": matched_source,
        "detected_policy_type": detected_policy_type,
        "metadata": {
            "classified_at": datetime.now(timezone.utc).isoformat(),
            "classification_method": "rule-based-v2",
            "url_domain": domain,
            "file_size": file_size,
            "policy_type": detected_policy_type,
        },
    }


def extract_pdf_text_sample(file_path: Path, max_chars: int = 2000) -> Optional[str]:
    """
    Try to extract text from the first pages of a PDF for classification.
    Falls back gracefully if PyPDF2/pdfplumber not available.
    """
    try:
        # Try PyPDF2 first (commonly installed)
        import PyPDF2
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page_num in range(min(3, len(reader.pages))):
                page_text = reader.pages[page_num].extract_text() or ""
                text += page_text
                if len(text) >= max_chars:
                    break
            return text[:max_chars] if text.strip() else None
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"PyPDF2 text extraction failed for {file_path}: {e}")
    
    try:
        # Fallback: try pdfplumber
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page_num in range(min(3, len(pdf.pages))):
                page_text = pdf.pages[page_num].extract_text() or ""
                text += page_text
                if len(text) >= max_chars:
                    break
            return text[:max_chars] if text.strip() else None
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pdfplumber text extraction failed for {file_path}: {e}")
    
    # No PDF library available — classify from URL/filename only
    return None


# ============================================================================
# MAIN CRAWL EXECUTION ENGINE
# ============================================================================

def _mark_crawl_failed(session_id: int, reason: str) -> None:
    """Best-effort failure state persistence for crawl sessions."""
    from app.database import get_db_context

    try:
        with get_db_context() as db:
            session = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
            if not session:
                logger.error(
                    f"[Crawl {session_id}] Unable to mark failed; session not found "
                    f"(reason={reason})"
                )
                return

            session.status = "failed"
            session.completed_at = datetime.now(timezone.utc)
            session.errors_count = (session.errors_count or 0) + 1
            db.commit()

            logger.info(
                f"[Crawl {session_id}] Marked session as failed "
                f"(reason={reason}, errors_count={session.errors_count})"
            )
    except Exception:
        logger.error(
            f"[Crawl {session_id}] Failed to persist failed status (reason={reason})",
            exc_info=True,
        )


def run_crawl_session(session_id: int):
    """
    Execute a crawl session with own DB connection.
    
    CRITICAL IMPROVEMENTS FROM V5:
    1. Registers/unregisters from active crawl tracking
    2. Better structured logging with crawl_id context
    3. Improved error handling with specific exceptions
    4. Graceful cleanup on all exit paths
    5. More defensive duplicate checking
    6. Better progress tracking
    7. Memory-efficient operations
    
    This is the main ingestion pipeline:
    1. Check concurrency limits
    2. Update status to 'running'
    3. Crawl each seed URL
    4. Apply filters
    5. Download PDFs
    6. Store metadata with deduplication
    7. Update progress
    8. Clean up resources
    """
    # Import here to avoid circular dependency
    from app.database import get_db_context
    
    logger.info(f"[Crawl {session_id}] Starting crawl session")
    
    # CRITICAL: Track active crawl for concurrency limits
    register_active_crawl(session_id)
    
    http_session = None
    
    try:
        # CRITICAL: Create own DB session for background task
        with get_db_context() as db:
            session = db.query(CrawlSession).filter(
                CrawlSession.id == session_id
            ).first()
            
            if not session:
                logger.error(f"[Crawl {session_id}] Crawl session not found in database")
                return
            
            # Update status to running
            session.status = "running"
            session.started_at = datetime.now(timezone.utc)
            db.commit()
            
            logger.info(
                f"[Crawl {session_id}] Configuration: "
                f"country={session.country}, max_pages={session.max_pages}, "
                f"max_minutes={session.max_minutes}, seeds={len(session.seed_urls)}, "
                f"filters={len(session.keyword_filters)}"
            )
            
            # Calculate time limit
            time_limit = None
            if session.max_minutes:
                time_limit = datetime.now(timezone.utc) + timedelta(
                    minutes=session.max_minutes
                )
                logger.info(
                    f"[Crawl {session_id}] Time limit: {session.max_minutes} minutes "
                    f"(until {time_limit.isoformat()})"
                )
            
            # Create reusable HTTP session with connection pooling
            # v7: Disable SSL verification to handle sites with bad/mismatched certs (e.g. cigna.co.nz)
            http_session = get_session_with_retries(verify_ssl=False)
            
            all_pdf_urls: Set[str] = set()
            total_pages = 0
            global_visited: Set[str] = set()  # Share visited URLs across seeds
            
            # CRITICAL FIX: Budget pages PER SEED to avoid spending all on one domain
            num_seeds = len(session.seed_urls)
            pages_per_seed = max(3, session.max_pages // max(1, num_seeds))
            remaining_budget = session.max_pages
            
            crawl_log(session_id, "info",
                f"Starting crawl: {num_seeds} seeds, {session.max_pages} total pages, "
                f"{pages_per_seed} pages/seed")
            logger.info(
                f"[Crawl {session_id}] Page budget: {session.max_pages} total, "
                f"{pages_per_seed}/seed ({num_seeds} seeds)")
            
            # Crawl each seed URL with budgeted pages
            for idx, seed_url in enumerate(session.seed_urls, 1):
                if time_limit and datetime.now(timezone.utc) > time_limit:
                    crawl_log(session_id, "warn", f"Time limit reached at seed {idx}/{num_seeds}")
                    break
                
                if remaining_budget <= 0:
                    crawl_log(session_id, "info", f"Page budget exhausted at seed {idx}/{num_seeds}")
                    break
                
                seed_budget = min(pages_per_seed, remaining_budget)
                seed_domain = urlparse(seed_url).netloc
                
                crawl_log(session_id, "info",
                    f"[{idx}/{num_seeds}] Crawling {seed_domain} ({seed_budget} pages)")
                logger.info(
                    f"[Crawl {session_id}] Seed {idx}/{num_seeds}: "
                    f"{seed_url} (budget={seed_budget})")
                
                pdf_urls, pages_crawled = crawl_domain(
                    seed_url=seed_url,
                    max_pages=seed_budget,
                    keyword_filters=session.keyword_filters,
                    policy_types=session.policy_types,
                    session=http_session,
                    crawl_id=session_id,
                    time_limit=time_limit,
                    global_visited=global_visited,
                )
                
                all_pdf_urls.update(pdf_urls)
                total_pages += pages_crawled
                remaining_budget -= pages_crawled
                
                # Update progress based on seeds completed (smoother than pages)
                session.pages_scanned = total_pages
                session.pdfs_found = len(all_pdf_urls)
                # Phase 1 (scanning): 0-50%, based on seeds completed
                seed_progress = int((idx / max(1, num_seeds)) * 50)
                session.progress_pct = min(50, seed_progress)
                db.commit()
                
                crawl_log(session_id, "info",
                    f"[{idx}/{num_seeds}] {seed_domain}: {len(pdf_urls)} PDFs, "
                    f"{pages_crawled} pages (total: {len(all_pdf_urls)} PDFs)")
                logger.info(
                    f"[Crawl {session_id}] Seed {idx} done: "
                    f"{len(pdf_urls)} PDFs, {pages_crawled} pages "
                    f"(running total: {total_pages}/{session.max_pages})")
            
            # Download PDFs and create document records
            downloaded_count = 0
            filtered_count = 0
            duplicate_count = 0
            error_count = 0
            
            crawl_log(session_id, "info",
                f"Phase 2: Downloading {len(all_pdf_urls)} PDF candidates")
            logger.info(
                f"[Crawl {session_id}] Starting PDF downloads "
                f"({len(all_pdf_urls)} candidates)"
            )
            
            for idx, pdf_url in enumerate(all_pdf_urls, 1):
                # Check time limit
                if time_limit and datetime.now(timezone.utc) > time_limit:
                    logger.warning(
                        f"[Crawl {session_id}] Time limit reached during downloads "
                        f"({idx}/{len(all_pdf_urls)})"
                    )
                    break
                
                # Re-apply filters to determine policy type
                is_valid, policy_type = is_valid_document(
                    pdf_url,
                    session.keyword_filters,
                    session.policy_types
                )
                
                if not is_valid:
                    filtered_count += 1
                    logger.debug(
                        f"[Crawl {session_id}] Filtered out on re-check: {pdf_url}"
                    )
                    continue
                
                # Extract insurer name
                insurer = extract_insurer_name(pdf_url)
                
                # Generate safe filename
                url_path = urlparse(pdf_url).path
                filename = os.path.basename(url_path) or "document.pdf"
                filename = sanitize_filename(filename)
                
                if not filename.endswith('.pdf'):
                    filename += '.pdf'
                
                # Ensure unique filename (prevent overwrites)
                base_name = filename.replace('.pdf', '')
                counter = 1
                while True:
                    test_path = RAW_STORAGE_DIR / insurer / filename
                    if not test_path.exists():
                        break
                    filename = f"{base_name}_{counter}.pdf"
                    counter += 1
                
                # Download PDF with streaming - initially save to insurer folder
                local_path = RAW_STORAGE_DIR / insurer / filename
                download_result = download_pdf_streaming(
                    pdf_url, local_path, http_session, session_id
                )
                
                if download_result:
                    try:
                        # CRITICAL: Check for duplicate BEFORE insert
                        existing_doc = db.query(Document).filter(
                            Document.file_hash == download_result['file_hash']
                        ).with_for_update().first()
                        
                        if existing_doc:
                            # Check if existing file still exists on disk
                            existing_file_path = None
                            if existing_doc.local_file_path:
                                existing_file_path = Path(existing_doc.local_file_path)
                            
                            if existing_file_path and existing_file_path.exists():
                                # True duplicate - file exists, skip
                                logger.info(
                                    f"[Crawl {session_id}] Duplicate PDF "
                                    f"(hash match, file exists): {pdf_url}"
                                )
                                try:
                                    if local_path.exists():
                                        local_path.unlink()
                                except Exception as e:
                                    logger.error(f"[Crawl {session_id}] Failed to delete duplicate: {e}")
                                
                                duplicate_count += 1
                                filtered_count += 1
                                continue
                            else:
                                # File MISSING - update old record with fresh download
                                logger.warning(
                                    f"[Crawl {session_id}] Hash match but file missing! "
                                    f"Re-downloading doc #{existing_doc.id}: {pdf_url}"
                                )
                                existing_doc.local_file_path = str(local_path)
                                existing_doc.source_url = pdf_url
                                existing_doc.file_size = download_result['file_size']
                                existing_doc.crawl_session_id = session_id
                                db.commit()
                                download_count += 1
                                logger.info(
                                    f"[Crawl {session_id}] ✅ Re-downloaded doc #{existing_doc.id}: "
                                    f"{filename} ({download_result['file_size'] / 1024:.1f}KB)"
                                )
                                continue
                        
                        # ============================================
                        # CLASSIFICATION PIPELINE
                        # ============================================
                        
                        # Try to extract text from PDF for better classification
                        pdf_text = extract_pdf_text_sample(local_path)
                        
                        # Run classification engine
                        classification_result = classify_document(
                            url=pdf_url,
                            filename=filename,
                            policy_type=policy_type or "General",
                            file_size=download_result['file_size'],
                            pdf_text_sample=pdf_text,
                        )
                        
                        # Use better insurer name if found
                        doc_insurer = classification_result.get("insurer_name") or insurer
                        
                        # Use detected policy type if available
                        doc_policy_type = classification_result.get("detected_policy_type") or policy_type or "General"
                        
                        # Move file to policy_type folder for better organization
                        policy_dir = RAW_STORAGE_DIR / doc_policy_type
                        policy_dir.mkdir(parents=True, exist_ok=True)
                        new_local_path = policy_dir / local_path.name
                        
                        # Handle filename collision in policy_type folder
                        if new_local_path.exists() and new_local_path != local_path:
                            base = local_path.stem
                            ext = local_path.suffix
                            move_counter = 1
                            while new_local_path.exists():
                                new_local_path = policy_dir / f"{base}_{move_counter}{ext}"
                                move_counter += 1
                        
                        try:
                            if local_path.exists() and local_path != new_local_path:
                                import shutil
                                shutil.move(str(local_path), str(new_local_path))
                                local_path = new_local_path
                        except Exception as move_err:
                            logger.warning(
                                f"[Crawl {session_id}] Could not move file to policy_type folder: {move_err}. "
                                f"Keeping in original location."
                            )
                        
                        logger.info(
                            f"[Crawl {session_id}] Classified '{filename}': "
                            f"{classification_result['classification']} "
                            f"({classification_result['confidence']*100:.0f}% confidence, "
                            f"policy_type={doc_policy_type}, "
                            f"status={classification_result['status']})"
                        )
                        
                        # Create document record with classification
                        doc = Document(
                            crawl_session_id=session.id,
                            source_url=pdf_url,
                            insurer=doc_insurer,
                            local_file_path=str(local_path),
                            file_size=download_result['file_size'],
                            file_hash=download_result['file_hash'],
                            country=session.country,
                            policy_type=doc_policy_type,
                            document_type=classification_result["classification"],
                            classification=classification_result["classification"],
                            confidence=classification_result["confidence"],
                            status=classification_result["status"],
                            warnings=classification_result["warnings"] if classification_result["warnings"] else None,
                            metadata_json=classification_result["metadata"],
                        )
                        
                        db.add(doc)
                        downloaded_count += 1
                        
                        # Update session stats
                        session.pdfs_downloaded = downloaded_count
                        session.progress_pct = 50 + min(
                            50,
                            int((idx / max(len(all_pdf_urls), 1)) * 50)
                        )
                        db.commit()
                        
                        if downloaded_count % 10 == 0:
                            logger.info(
                                f"[Crawl {session_id}] Progress: "
                                f"{downloaded_count}/{len(all_pdf_urls)} downloaded, "
                                f"{duplicate_count} duplicates, {filtered_count} filtered"
                            )
                            crawl_log(session_id, "info",
                                f"Downloaded {downloaded_count}/{len(all_pdf_urls)} PDFs "
                                f"({duplicate_count} dups, {filtered_count} filtered)")
                    
                    except SQLAlchemyError as e:
                        logger.error(
                            f"[Crawl {session_id}] Database error processing {pdf_url}: {e}",
                            exc_info=True
                        )
                        error_count += 1
                        session.errors_count = (session.errors_count or 0) + 1
                        db.commit()
                
                else:
                    error_count += 1
                    session.errors_count = (session.errors_count or 0) + 1
                    db.commit()
            
            # Mark as completed
            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)
            session.progress_pct = 100
            session.pdfs_filtered = filtered_count
            db.commit()
            
            duration = (session.completed_at - session.started_at).total_seconds()
            
            logger.info(
                f"[Crawl {session_id}] Crawl session completed successfully: "
                f"{downloaded_count} PDFs downloaded, "
                f"{duplicate_count} duplicates skipped, "
                f"{filtered_count} filtered, "
                f"{error_count} errors, "
                f"duration={duration:.1f}s"
            )
            crawl_log(session_id, "info",
                f"✅ Crawl complete! {downloaded_count} downloaded, "
                f"{duplicate_count} duplicates, {filtered_count} filtered, "
                f"{error_count} errors ({duration:.0f}s)")
    
    except SQLAlchemyError as e:
        logger.error(
            f"[Crawl {session_id}] Database error during crawl: {e}",
            exc_info=True
        )
        _mark_crawl_failed(session_id, "database_error")
    
    except Exception as e:
        logger.error(
            f"[Crawl {session_id}] Unexpected error during crawl: {e}",
            exc_info=True
        )
        _mark_crawl_failed(session_id, "unexpected_error")
    
    finally:
        # CRITICAL: Clean up resources
        if http_session:
            try:
                http_session.close()
                logger.debug(f"[Crawl {session_id}] Closed HTTP session")
            except Exception as e:
                logger.error(
                    f"[Crawl {session_id}] Error closing HTTP session: {e}"
                )

        # Best-effort cache invalidation so dashboards reflect crawl updates quickly.
        try:
            invalidate_cache_prefix("stats:")
            invalidate_cache_prefix("documents:")
        except Exception as e:
            logger.debug(f"[Crawl {session_id}] Cache invalidation failed: {e}")
        
        # CRITICAL: Unregister from active crawls
        unregister_active_crawl(session_id)


# ============================================================================
# QUERY FUNCTIONS
# ============================================================================

def get_crawl_status(db: Session, session_id: int) -> Optional[CrawlSession]:
    """Get crawl session status."""
    return db.query(CrawlSession).filter(CrawlSession.id == session_id).first()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'create_crawl_session',
    'run_crawl_session',
    'get_crawl_status',
    'can_start_crawl',
    'get_active_crawl_count',
    'classify_document',
    'extract_pdf_text_sample',
]
