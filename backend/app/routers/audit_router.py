"""Audit log API endpoint."""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, AuditLog
from app.auth import get_current_user

router = APIRouter(prefix="/api", tags=["audit"])
logger = logging.getLogger(__name__)


@router.get("/audit-log")
def get_audit_log(
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
    action: str = Query(None),
    user_id: int = Query(None),
    document_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return paginated audit log entries."""
    try:
        query = db.query(AuditLog)

        if action:
            query = query.filter(AuditLog.action == action)
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if document_id:
            query = query.filter(AuditLog.document_id == document_id)

        total = query.count()

        entries = (
            query.order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return {
            "entries": [
                {
                    "id": e.id,
                    "timestamp": e.created_at.isoformat() if e.created_at else None,
                    "user": e.user_name or "system",
                    "action": e.action,
                    "details": e.details,
                    "document_id": e.document_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entries
            ],
            "total": total,
            "page": (skip // limit) + 1 if limit else 1,
            "page_size": limit,
        }

    except Exception as e:
        logger.error(f"Error fetching audit log: {e}", exc_info=True)
        return {
            "entries": [],
            "total": 0,
            "page": 1,
            "page_size": limit,
        }
