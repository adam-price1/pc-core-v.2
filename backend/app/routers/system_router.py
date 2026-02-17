"""System management API endpoints."""
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Document
from app.services import document_service
from app.auth import get_current_user

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger(__name__)


class ResetResponse(BaseModel):
    """System reset response."""
    status: str
    crawl_sessions_deleted: int
    documents_deleted: int
    storage_items_deleted: int
    storage_directories_deleted: int
    message: str


@router.delete("/reset", response_model=ResetResponse)
def reset_system(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reset the entire system.
    
    WARNING: This will:
    - Delete all crawl sessions
    - Delete all documents (DB records)
    - Delete all downloaded PDF files
    - Recreate empty storage structure
    
    Only admins can perform this operation.
    """
    # Check if user is admin
    if current_user.role not in ("admin", "reviewer"):
        raise HTTPException(
            status_code=403,
            detail="Only administrators can reset the system"
        )
    
    # Perform reset
    result = document_service.reset_system(db)
    
    return ResetResponse(
        status=result["status"],
        crawl_sessions_deleted=result["crawl_sessions_deleted"],
        documents_deleted=result["documents_deleted"],
        storage_items_deleted=result["storage_items_deleted"],
        storage_directories_deleted=result["storage_items_deleted"],
        message=f"System reset completed. Deleted {result['crawl_sessions_deleted']} crawl sessions, "
                f"{result['documents_deleted']} documents, and {result['storage_items_deleted']} storage items."
    )


@router.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "PolicyCheck v6"}


@router.delete("/purge-orphans")
def purge_orphan_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove document DB records whose PDF files no longer exist on disk."""
    if current_user.role not in ("admin", "reviewer"):
        raise HTTPException(403, "Only administrators can purge orphans")
    
    all_docs = db.query(Document).all()
    orphans = []
    valid = []
    for doc in all_docs:
        if doc.local_file_path and Path(doc.local_file_path).exists():
            valid.append(doc)
        else:
            orphans.append(doc)
    
    for orphan in orphans:
        db.delete(orphan)
    db.commit()
    
    logger.info(f"Purged {len(orphans)} orphan documents, {len(valid)} valid remain")
    
    return {
        "status": "success",
        "orphans_deleted": len(orphans),
        "valid_documents": len(valid),
        "message": f"Purged {len(orphans)} orphan records. {len(valid)} valid documents remain."
    }
