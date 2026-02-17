"""Production-hardened crawl management API endpoints."""
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.cache import invalidate_cache_prefix
from app.database import get_db
from app.models import User, Document, CrawlSession
from app.services import crawl_service
from app.services import seed_url_service
from app.auth import get_current_user

router = APIRouter(prefix="/api/crawl", tags=["crawl"])
logger = logging.getLogger(__name__)


# ============================================================================
# SCHEMAS
# ============================================================================

class CrawlConfigRequest(BaseModel):
    country: str = Field(..., min_length=2, max_length=10)
    max_pages: int = Field(default=1000, ge=1, le=500000)
    max_time: int = Field(default=60, ge=1, le=180, alias="max_minutes")
    seed_urls: List[str] = Field(..., min_length=1)
    policy_types: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list, alias="keyword_filters")

    class Config:
        populate_by_name = True

    @field_validator("seed_urls")
    @classmethod
    def validate_seed_urls(cls, v):
        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"Invalid URL: {url}")
        return v

    @field_validator("keywords", mode="before")
    @classmethod
    def validate_keywords(cls, v):
        if v is None:
            return []
        return [k.strip() for k in v if k and k.strip()]


class CrawlResponse(BaseModel):
    crawl_id: int
    status: str
    message: str
    active_crawls: int
    max_concurrent_crawls: int


class CrawlStatusResponse(BaseModel):
    id: int
    status: str
    country: str
    progress_pct: int
    pages_scanned: int
    pdfs_found: int
    pdfs_downloaded: int
    pdfs_filtered: int
    errors_count: int
    max_pages: Optional[int] = None
    current_phase: Optional[str] = None
    phase_detail: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    seed_urls_crawled: Optional[List[str]] = None
    insurers_list: Optional[List[str]] = None

    class Config:
        from_attributes = True


class CrawlDeleteResponse(BaseModel):
    status: str
    crawl_id: int
    documents_deleted: int
    files_deleted: int
    message: str


# ============================================================================
# HELPER
# ============================================================================

def _start_crawl_logic(
    config: CrawlConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
) -> CrawlResponse:
    """Shared logic for starting a crawl."""
    logger.info(
        f"Crawl start by {current_user.username}: country={config.country}, "
        f"seeds={len(config.seed_urls)}, max_pages={config.max_pages}"
    )

    can_start, reason = crawl_service.can_start_crawl()
    if not can_start:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Maximum concurrent crawls reached",
                "reason": reason,
                "active_crawls": crawl_service.get_active_crawl_count(),
            },
        )

    try:
        session = crawl_service.create_crawl_session(
            db=db,
            user=current_user,
            country=config.country,
            max_pages=config.max_pages,
            max_minutes=config.max_time,
            seed_urls=config.seed_urls,
            policy_types=config.policy_types,
            keyword_filters=config.keywords,
        )
        background_tasks.add_task(crawl_service.run_crawl_session, session.id)
        active = crawl_service.get_active_crawl_count()
        invalidate_cache_prefix("stats:")
        invalidate_cache_prefix("documents:")

        return CrawlResponse(
            crawl_id=session.id,
            status=session.status,
            message=f"Crawl session {session.id} started",
            active_crawls=active,
            max_concurrent_crawls=crawl_service.MAX_CONCURRENT_CRAWLS,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting crawl: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start crawl")


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("", response_model=CrawlResponse)
def start_crawl_root(
    config: CrawlConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new crawl session (POST /api/crawl)."""
    return _start_crawl_logic(config, background_tasks, db, current_user)


@router.post("/start", response_model=CrawlResponse)
def start_crawl(
    config: CrawlConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new crawl session (POST /api/crawl/start)."""
    return _start_crawl_logic(config, background_tasks, db, current_user)


def _build_crawl_response(session) -> CrawlStatusResponse:
    """Build a CrawlStatusResponse from a CrawlSession model."""
    progress = session.progress_pct or 0
    pages = session.pages_scanned or 0
    pdfs_found = session.pdfs_found or 0
    pdfs_downloaded = session.pdfs_downloaded or 0
    max_pages = session.max_pages or 200
    num_seeds = len(session.seed_urls) if session.seed_urls else 0

    # Derive current phase from progress
    if session.status == "completed":
        current_phase = "Complete"
        phase_detail = f"{pdfs_downloaded} PDFs downloaded"
    elif session.status == "failed":
        current_phase = "Failed"
        phase_detail = f"After {pages} pages"
    elif progress < 50:
        current_phase = "Scanning"
        phase_detail = f"{pages}/{max_pages} pages · {pdfs_found} PDFs found"
    elif progress < 100:
        current_phase = "Downloading"
        phase_detail = f"{pdfs_downloaded}/{pdfs_found} PDFs downloaded"
    else:
        current_phase = "Finishing"
        phase_detail = f"{pdfs_downloaded} PDFs"

    return CrawlStatusResponse(
        id=session.id,
        status=session.status,
        country=session.country,
        progress_pct=progress,
        pages_scanned=pages,
        pdfs_found=pdfs_found,
        pdfs_downloaded=pdfs_downloaded,
        pdfs_filtered=session.pdfs_filtered or 0,
        errors_count=session.errors_count or 0,
        max_pages=max_pages,
        current_phase=current_phase,
        phase_detail=phase_detail,
        started_at=session.started_at.isoformat() if session.started_at else None,
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        seed_urls_crawled=session.seed_urls if session.seed_urls else None,
        insurers_list=seed_url_service.resolve_insurers_from_urls(session.seed_urls or [], session.country) if session.seed_urls else None,
    )


@router.get("/{crawl_id}/status", response_model=CrawlStatusResponse)
def get_crawl_status(
    crawl_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get crawl session status."""
    session = crawl_service.get_crawl_status(db, crawl_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Crawl {crawl_id} not found")
    return _build_crawl_response(session)


@router.get("/{crawl_id}/logs")
def get_crawl_logs(
    crawl_id: int,
    since: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get live crawl log entries. Use since=N to get entries after index N."""
    logs = crawl_service.get_crawl_logs(crawl_id, since=since)
    return {
        "crawl_id": crawl_id,
        "since": since,
        "total": since + len(logs),
        "entries": logs,
    }


@router.get("/{crawl_id}/results")
def get_crawl_results(
    crawl_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get documents produced by a crawl session."""
    session = crawl_service.get_crawl_status(db, crawl_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Crawl {crawl_id} not found")

    docs = db.query(Document).filter(Document.crawl_session_id == crawl_id).all()

    return {
        "crawl_id": crawl_id,
        "status": session.status,
        "total": len(docs),
        "documents": [
            {
                "id": d.id,
                "source_url": d.source_url,
                "insurer": d.insurer,
                "country": d.country,
                "policy_type": d.policy_type,
                "document_type": d.document_type,
                "classification": d.classification,
                "confidence": d.confidence,
                "file_size": d.file_size,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
    }


@router.delete("/{crawl_id}", response_model=CrawlDeleteResponse)
def delete_crawl(
    crawl_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a crawl session and all its associated data.

    Clears DB entries, metadata, and stored PDFs.
    """
    logger.info(f"Delete crawl {crawl_id} requested by {current_user.username}")

    session = db.query(CrawlSession).filter(CrawlSession.id == crawl_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Crawl {crawl_id} not found")

    if session.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a running crawl. Wait for it to complete or fail.",
        )

    docs = db.query(Document).filter(Document.crawl_session_id == crawl_id).all()
    doc_count = len(docs)

    files_deleted = 0
    for doc in docs:
        try:
            file_path = Path(doc.local_file_path)
            if file_path.exists():
                file_path.unlink()
                files_deleted += 1
                logger.debug(f"Deleted file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete file for doc {doc.id}: {e}")

    try:
        db.delete(session)
        db.commit()
        logger.info(f"Crawl {crawl_id} deleted: {doc_count} docs, {files_deleted} files")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete crawl {crawl_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete crawl session")

    invalidate_cache_prefix("stats:")
    invalidate_cache_prefix("documents:")

    return CrawlDeleteResponse(
        status="success",
        crawl_id=crawl_id,
        documents_deleted=doc_count,
        files_deleted=files_deleted,
        message=f"Crawl {crawl_id} deleted. {doc_count} documents and {files_deleted} files removed.",
    )


@router.get("/latest")
def get_latest_crawl(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent crawl session (running preferred, else latest)."""
    # Try to find a running crawl first
    running = (
        db.query(CrawlSession)
        .filter(CrawlSession.user_id == current_user.id, CrawlSession.status == "running")
        .order_by(CrawlSession.created_at.desc())
        .first()
    )
    session = running
    if not session:
        session = (
            db.query(CrawlSession)
            .filter(CrawlSession.user_id == current_user.id)
            .order_by(CrawlSession.created_at.desc())
            .first()
        )
    if not session:
        return {"crawl": None}
    return {
        "crawl": CrawlStatusResponse(
            id=session.id,
            status=session.status,
            country=session.country,
            progress_pct=session.progress_pct or 0,
            pages_scanned=session.pages_scanned or 0,
            pdfs_found=session.pdfs_found or 0,
            pdfs_downloaded=session.pdfs_downloaded or 0,
            pdfs_filtered=session.pdfs_filtered or 0,
            errors_count=session.errors_count or 0,
            started_at=session.started_at.isoformat() if session.started_at else None,
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
        )
    }


@router.get("/sessions", response_model=List[CrawlStatusResponse])
def list_crawl_sessions(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List crawl sessions for the current user."""
    sessions = (
        db.query(CrawlSession)
        .filter(CrawlSession.user_id == current_user.id)
        .order_by(CrawlSession.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [_build_crawl_response(s) for s in sessions]


@router.get("/active/count")
def get_active_count(current_user: User = Depends(get_current_user)):
    """Get number of currently active crawls."""
    active = crawl_service.get_active_crawl_count()
    mx = crawl_service.MAX_CONCURRENT_CRAWLS
    return {
        "active_crawls": active,
        "max_concurrent_crawls": mx,
        "available_slots": mx - active,
        "at_capacity": active >= mx,
    }


@router.post("/test-url")
def test_crawl_url(
    url: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test if a URL can be crawled and what content it returns."""
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    
    result = {
        "url": url,
        "can_access": False,
        "status_code": None,
        "content_type": None,
        "robots_allowed": False,
        "links_found": 0,
        "pdf_links": [],
        "error": None,
    }
    
    try:
        # Check robots.txt
        session = crawl_service.get_session_with_retries()
        result["robots_allowed"] = crawl_service.can_fetch(url, session)
        
        if not result["robots_allowed"]:
            result["error"] = "Blocked by robots.txt"
            return result
        
        # Try to fetch the URL
        response = session.get(url, timeout=10)
        result["status_code"] = response.status_code
        result["content_type"] = response.headers.get("Content-Type", "")
        
        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}"
            return result
        
        result["can_access"] = True
        
        # Parse HTML if applicable
        if "text/html" in result["content_type"].lower():
            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.find_all("a", href=True)
            result["links_found"] = len(links)
            
            # Find PDF links
            for link in links:
                href = link["href"].strip()
                if href:
                    full_url = urljoin(url, href)
                    if full_url.lower().endswith(".pdf"):
                        result["pdf_links"].append(full_url)
        
        return result
        
    except Exception as e:
        result["error"] = str(e)
        return result


# ============================================================================
# SEED URL DISCOVERY
# ============================================================================

@router.get("/seed-urls")
def get_seed_urls(
    country: str = Query("NZ", description="Country code (NZ, AU, UK)"),
    policy_type: Optional[str] = Query(None, description="Filter by policy type"),
    insurer: Optional[str] = Query(None, description="Filter by insurer name"),
    validate: bool = Query(False, description="Validate URLs are reachable (slower)"),
    current_user: User = Depends(get_current_user),
):
    """
    Get curated seed URLs for insurance crawling.
    
    Returns list of insurers with their seed URLs, filtered by country/policy_type/insurer.
    """
    results = seed_url_service.get_seed_urls(
        country=country,
        policy_type=policy_type,
        insurer=insurer,
        validate=validate,
    )
    
    return {
        "country": country,
        "filters": {
            "policy_type": policy_type,
            "insurer": insurer,
        },
        "total_insurers": len(results),
        "total_urls": sum(len(r["seed_urls"]) for r in results),
        "insurers": results,
    }


@router.get("/seed-urls/countries")
def get_supported_countries(
    current_user: User = Depends(get_current_user),
):
    """Get list of supported countries for seed URL discovery."""
    return {
        "countries": seed_url_service.get_supported_countries(),
    }


# ============================================================================
# CUSTOM INSURER MANAGEMENT
# ============================================================================

class AddCustomInsurerRequest(BaseModel):
    country: str = Field(..., min_length=2, max_length=10)
    insurer_name: str = Field(..., min_length=1, max_length=200)
    seed_urls: List[str] = Field(..., min_length=1)
    policy_types: Optional[List[str]] = None

    @field_validator("seed_urls")
    @classmethod
    def validate_urls(cls, v):
        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"Invalid URL: {url}")
        return v


@router.post("/custom-insurers")
def add_custom_insurer(
    req: AddCustomInsurerRequest,
    current_user: User = Depends(get_current_user),
):
    """Add a custom insurer with seed URLs (persists across restarts)."""
    result = seed_url_service.add_custom_insurer(
        country=req.country,
        insurer_name=req.insurer_name,
        seed_urls=req.seed_urls,
        policy_types=req.policy_types,
    )
    return {"status": "ok", "message": f"Added custom insurer: {req.insurer_name}", "insurer": result}


@router.delete("/custom-insurers/{country}/{insurer_name}")
def remove_custom_insurer(
    country: str,
    insurer_name: str,
    current_user: User = Depends(get_current_user),
):
    """Remove a custom insurer."""
    removed = seed_url_service.remove_custom_insurer(country, insurer_name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Custom insurer '{insurer_name}' not found for {country}")
    return {"status": "ok", "message": f"Removed custom insurer: {insurer_name}"}


@router.get("/custom-insurers")
def list_custom_insurers(
    country: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """List all custom insurers."""
    return seed_url_service.list_custom_insurers(country)
