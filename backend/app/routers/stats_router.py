"""Stats API endpoints — pipeline funnel and dashboard summary."""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.cache import get_cached_json, make_cache_key, set_cached_json
from app.config import CACHE_DEFAULT_TTL_SECONDS
from app.database import get_db
from app.models import User, CrawlSession, Document, AuditLog
from app.auth import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = logging.getLogger(__name__)
STATS_CACHE_TTL_SECONDS = min(max(CACHE_DEFAULT_TTL_SECONDS, 10), 300)


@router.get("/pipeline")
def get_pipeline_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return pipeline stage counts and funnel conversion rates."""
    cache_key = make_cache_key("stats", "pipeline", f"user:{current_user.id}")
    cached_payload = get_cached_json(cache_key)
    if cached_payload is not None:
        return cached_payload

    try:
        total_sessions = db.query(CrawlSession).count()
        running = db.query(CrawlSession).filter(CrawlSession.status == "running").count()
        completed = db.query(CrawlSession).filter(CrawlSession.status == "completed").count()
        failed = db.query(CrawlSession).filter(CrawlSession.status == "failed").count()

        total_docs = db.query(Document).count()
        pending = db.query(Document).filter(
            Document.status.in_(["pending", "needs-review"])
        ).count()
        auto_approved = db.query(Document).filter(Document.status == "auto-approved").count()
        validated = db.query(Document).filter(Document.status == "validated").count()
        rejected = db.query(Document).filter(Document.status == "rejected").count()

        # Aggregate scan numbers across sessions
        agg = db.query(
            func.coalesce(func.sum(CrawlSession.pages_scanned), 0),
            func.coalesce(func.sum(CrawlSession.pdfs_found), 0),
            func.coalesce(func.sum(CrawlSession.pdfs_downloaded), 0),
            func.coalesce(func.sum(CrawlSession.pdfs_filtered), 0),
        ).first()
        pages_scanned = int(agg[0])
        pdfs_found = int(agg[1])
        pdfs_downloaded = int(agg[2])
        pdfs_filtered = int(agg[3])

        stages = {
            "discovered": pages_scanned,
            "pdfs_found": pdfs_found,
            "downloaded": pdfs_downloaded,
            "filtered_out": pdfs_filtered,
            "stored": total_docs,
            "pending_review": pending,
            "auto_approved": auto_approved,
            "validated": validated,
            "rejected": rejected,
        }

        # Compute safe funnel rates
        def safe_rate(num, denom):
            return round((num / denom) * 100, 1) if denom else 0.0

        funnel_rates = {
            "discovered_to_pdfs_found": safe_rate(pdfs_found, pages_scanned),
            "pdfs_found_to_downloaded": safe_rate(pdfs_downloaded, pdfs_found),
            "downloaded_to_stored": safe_rate(total_docs, pdfs_downloaded),
            "stored_to_approved": safe_rate(auto_approved + validated, total_docs),
        }

        avg_conf_row = db.query(func.avg(Document.confidence)).scalar()

        result = {
            "stages": stages,
            "funnel_rates": funnel_rates,
            "total_processed": total_docs,
            "avg_confidence": round(float(avg_conf_row or 0), 3),
            "error_rate": safe_rate(failed, total_sessions),
        }
        set_cached_json(cache_key, result, STATS_CACHE_TTL_SECONDS)
        return result

    except Exception as e:
        logger.error(f"Error computing pipeline stats: {e}", exc_info=True)
        return {
            "stages": {},
            "funnel_rates": {},
            "total_processed": 0,
            "avg_confidence": 0,
            "error_rate": 0,
        }


@router.get("/dashboard")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return high-level dashboard statistics."""
    cache_key = make_cache_key("stats", "dashboard", f"user:{current_user.id}")
    cached_payload = get_cached_json(cache_key)
    if cached_payload is not None:
        return cached_payload

    try:
        total_docs = db.query(Document).count()
        pending = db.query(Document).filter(
            Document.status.in_(["pending", "needs-review"])
        ).count()
        auto_approved = db.query(Document).filter(Document.status == "auto-approved").count()
        validated = db.query(Document).filter(Document.status == "validated").count()
        rejected = db.query(Document).filter(Document.status == "rejected").count()

        by_classification = {}
        for row in db.query(Document.classification, func.count()).group_by(Document.classification).all():
            by_classification[row[0]] = row[1]

        by_country = {}
        for row in db.query(Document.country, func.count()).group_by(Document.country).all():
            by_country[row[0]] = row[1]

        recent_entries = (
            db.query(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(10)
            .all()
        )
        recent_activity = [
            {
                "id": e.id,
                "timestamp": e.created_at.isoformat() if e.created_at else None,
                "user": e.user_name or "system",
                "action": e.action,
                "details": e.details,
                "document_id": e.document_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in recent_entries
        ]

        result = {
            "total_documents": total_docs,
            "needs_review": pending,
            "auto_approved": auto_approved,
            "user_approved": validated,
            "by_classification": by_classification,
            "by_country": by_country,
            "recent_activity": recent_activity,
        }
        set_cached_json(cache_key, result, STATS_CACHE_TTL_SECONDS)
        return result

    except Exception as e:
        logger.error(f"Error computing dashboard stats: {e}", exc_info=True)
        return {
            "total_documents": 0,
            "needs_review": 0,
            "auto_approved": 0,
            "user_approved": 0,
            "by_classification": {},
            "by_country": {},
            "recent_activity": [],
        }
