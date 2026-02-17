"""
Production-hardened document management API endpoints.
Includes: filtering, auto-classification uploads, and approval workflows.
"""
import logging
import uuid
import shutil
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.cache import (
    get_cached_json,
    invalidate_cache_prefix,
    make_cache_key,
    set_cached_json,
)
from app.config import CACHE_DEFAULT_TTL_SECONDS, RAW_STORAGE_DIR
from app.database import get_db
from app.models import AuditLog, Document, User
from app.services import document_service
from app.services.crawl_service import classify_document, extract_pdf_text_sample, sanitize_filename
from app.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = logging.getLogger(__name__)
DOCUMENTS_CACHE_TTL_SECONDS = min(max(CACHE_DEFAULT_TTL_SECONDS, 15), 180)


# ============================================================================
# RESPONSE SCHEMAS (Fixes the 500 Error)
# ============================================================================

class DocumentResponse(BaseModel):
    id: int
    source_url: str
    insurer: Optional[str] = None
    local_file_path: str
    file_size: Optional[int] = None
    file_hash: Optional[str] = None
    country: str
    policy_type: Optional[str] = None
    document_type: Optional[str] = None
    classification: Optional[str] = None
    confidence: float = 0.0
    status: str
    metadata_json: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    crawl_session_id: Optional[int] = None

    class Config:
        from_attributes = True


class PaginatedDocumentResponse(BaseModel):
    """Paginated response for document listings."""
    documents: List[DocumentResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


def _write_audit(
    db: Session,
    current_user: User,
    action: str,
    details: dict,
    document_id: Optional[int] = None,
) -> None:
    """Persist audit log without breaking the main request path."""
    try:
        entry = AuditLog(
            action=action,
            details=details,
            user_id=current_user.id,
            user_name=current_user.username,
            document_id=document_id,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


# ============================================================================
# FILTER OPTIONS (Fixes the 404 Error)
# ============================================================================

@router.get("/filters/options")
def get_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get distinct values for filter dropdowns (Country, Insurer, Status, etc).
    """
    try:
        # Helper to get distinct non-null values
        def get_distinct(column):
            return [r[0] for r in db.query(column).distinct().order_by(column).all() if r[0]]

        return {
            "countries": get_distinct(Document.country),
            "insurers": get_distinct(Document.insurer),
            "policy_types": get_distinct(Document.policy_type),
            "statuses": get_distinct(Document.status),
            "classifications": get_distinct(Document.classification)
        }
    except Exception as e:
        logger.error(f"Error fetching filter options: {e}")
        return {
            "countries": [], "insurers": [], "policy_types": [], "statuses": [], "classifications": []
        }


# ============================================================================
# UPLOAD ENDPOINT
# ============================================================================

@router.post("/upload", status_code=status.HTTP_201_CREATED, response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    policy_type: str = Form("General"),
    country: str = Form("NZ"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual document upload with AUTO-CLASSIFICATION."""
    try:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are accepted")
        
        safe_filename = sanitize_filename(file.filename)
        save_dir = RAW_STORAGE_DIR / "Manual_Uploads"
        save_dir.mkdir(parents=True, exist_ok=True)
        
        save_path = save_dir / safe_filename
        counter = 1
        while save_path.exists():
            save_path = save_dir / f"{safe_filename.replace('.pdf', '')}_{counter}.pdf"
            counter += 1
            
        file_size = 0
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            file_size = save_path.stat().st_size
            
        pdf_text = extract_pdf_text_sample(save_path)
        
        classification_result = classify_document(
            url=f"manual-upload://{safe_filename}",
            filename=safe_filename,
            policy_type=policy_type,
            file_size=file_size,
            pdf_text_sample=pdf_text
        )
        
        doc = Document(
            source_url="manual_upload",
            insurer="Manual Upload",
            local_file_path=str(save_path),
            file_size=file_size,
            file_hash="manual_" + str(uuid.uuid4()),
            country=country,
            policy_type=classification_result["detected_policy_type"],
            document_type=classification_result["classification"],
            classification=classification_result["classification"],
            confidence=classification_result["confidence"],
            status=classification_result["status"],
            metadata_json=classification_result["metadata"],
            warnings=classification_result["warnings"]
        )
        
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        _write_audit(db, current_user, "document_upload", {
            "filename": safe_filename, 
            "size": file_size,
            "classification": classification_result["classification"]
        }, doc.id)
        
        invalidate_cache_prefix("documents")
        invalidate_cache_prefix("stats")

        return doc

    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(500, f"Upload failed: {str(e)}")


# ============================================================================
# READ / LIST ENDPOINTS
# ============================================================================

@router.get("", response_model=PaginatedDocumentResponse)
def get_documents(
    skip: int = 0,
    limit: int = 50,
    page: Optional[int] = Query(None, description="Page number (1-indexed)"),
    country: Optional[str] = None,
    status: Optional[str] = None,
    policy_type: Optional[str] = None,
    insurer: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get documents with filtering and search - returns paginated response."""
    # Handle page-based pagination (convert to offset)
    if page is not None and page > 0:
        skip = (page - 1) * limit
    
    query = db.query(Document)

    if country:
        query = query.filter(Document.country == country)
    if status:
        query = query.filter(Document.status == status)
    if policy_type:
        query = query.filter(Document.policy_type == policy_type)
    if insurer:
        query = query.filter(Document.insurer == insurer)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Document.insurer.ilike(search_term)) | 
            (Document.source_url.ilike(search_term)) |
            (Document.classification.ilike(search_term))
        )

    # Get total count before pagination
    total = query.count()
    
    query = query.order_by(
        (Document.status == 'pending').desc(),
        (Document.status == 'needs-review').desc(), 
        Document.created_at.desc()
    )

    docs = query.offset(skip).limit(limit).all()
    
    return {
        "documents": docs,
        "total": total,
        "limit": limit,
        "offset": skip,
        "has_more": (skip + len(docs)) < total
    }


@router.get("/stats/summary")
def get_document_stats_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stats = document_service.get_document_stats(db)
    return stats


@router.get("/download-all/zip")
def download_all_zip(
    crawl_session_id: Optional[int] = Query(None),
    country: Optional[str] = Query(None),
    policy_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    insurer: Optional[str] = Query(None),
    classification: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download filtered documents as a ZIP file (streaming)."""
    zip_stream = document_service.create_download_zip_stream(
        db=db,
        crawl_session_id=crawl_session_id,
        country=country,
        policy_type=policy_type,
        status=status,
        insurer=insurer,
        classification=classification,
        search=search,
        min_confidence=min_confidence,
    )
    if zip_stream is None:
        raise HTTPException(
            404,
            "No downloadable files found. Document records exist in the database "
            "but the actual PDF files may be missing from storage. "
            "Try running a new crawl to re-download the documents."
        )

    from datetime import date
    # Build filename with filter info
    filter_parts = []
    if country:
        filter_parts.append(country)
    if policy_type:
        filter_parts.append(policy_type.replace(" ", "_"))
    if status:
        filter_parts.append(status)
    
    filter_str = "_".join(filter_parts) if filter_parts else "all"
    filename = f"policycheck_{filter_str}_{date.today().isoformat()}.zip"

    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


# ============================================================================
# ACTION ENDPOINTS
# ============================================================================

@router.post("/{document_id}/approve")
@router.put("/{document_id}/approve")
def approve_document(
    document_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
        
    doc.status = "validated"
    doc.updated_at = datetime.utcnow()
    db.commit()
    
    _write_audit(db, current_user, "approve_document", {"previous_status": "manually_approved"}, doc.id)
    invalidate_cache_prefix("documents")
    invalidate_cache_prefix("stats")
    return {"status": "success"}

@router.post("/{document_id}/reject")
@router.put("/{document_id}/reject")
def reject_document(
    document_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
        
    doc.status = "rejected"
    doc.updated_at = datetime.utcnow()
    db.commit()
    
    _write_audit(db, current_user, "reject_document", {}, doc.id)
    invalidate_cache_prefix("documents")
    invalidate_cache_prefix("stats")
    return {"status": "success"}

@router.put("/{document_id}/archive")
@router.post("/{document_id}/archive")
def archive_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Archive/reject a document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    doc.status = "rejected"
    doc.updated_at = datetime.utcnow()
    db.commit()

    _write_audit(db, current_user, "archive_document", {}, doc.id)
    invalidate_cache_prefix("documents")
    invalidate_cache_prefix("stats")
    return {"status": "success"}


class ReclassifyRequest(BaseModel):
    classification: str


@router.put("/{document_id}/reclassify")
@router.post("/{document_id}/reclassify")
def reclassify_document(
    document_id: int,
    body: ReclassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reclassify a document and auto-approve it."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    old_classification = doc.classification
    doc.classification = body.classification
    doc.document_type = body.classification
    doc.status = "validated"
    doc.confidence = 1.0
    doc.updated_at = datetime.utcnow()
    db.commit()

    _write_audit(db, current_user, "reclassify_document", {
        "old_classification": old_classification,
        "new_classification": body.classification,
    }, doc.id)
    invalidate_cache_prefix("documents")
    invalidate_cache_prefix("stats")
    return {"status": "success", "classification": body.classification}

@router.get("/{document_id}/preview")
def preview_document(
    document_id: int,
    db: Session = Depends(get_db),
    token: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Serve PDF inline for browser preview (no download trigger)."""
    # If no current_user from header, try token from query param
    if not current_user and token:
        from app.auth import decode_token
        try:
            payload = decode_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    current_user = db.query(User).filter(User.username == username).first()
        except Exception:
            pass

    if not current_user:
        raise HTTPException(401, "Authentication required")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    file_path = document_service.get_document_file_path(doc)
    if not file_path:
        raise HTTPException(404, "PDF file not found on disk.")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{file_path.name}"'},
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    token: Optional[str] = Query(None), 
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    if not current_user and token:
        # Simple token logic could go here if needed
        pass
        
    if not current_user:
         raise HTTPException(401, "Authentication required")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    file_path = document_service.get_document_file_path(doc)
    if not file_path:
        logger.warning(
            f"Download failed for doc {document_id}: file missing from storage. "
            f"DB path: {doc.local_file_path}"
        )
        raise HTTPException(
            404,
            "PDF file not found on disk. The file may have been removed. "
            "Try re-running the crawl to re-download this document."
        )
        
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/pdf"
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently delete a document and its file."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Delete file from disk
    if doc.local_file_path:
        from pathlib import Path
        file_path = Path(doc.local_file_path)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete file for doc {document_id}: {e}")

    # Write audit log
    _write_audit(db, current_user, "document_deleted", document_id,
                 {"insurer": doc.insurer, "classification": doc.classification})

    # Delete from database
    db.delete(doc)
    db.commit()

    return {"status": "ok", "message": f"Document #{document_id} deleted"}