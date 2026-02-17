"""
ORM models for PolicyCheck v5 - Production ingestion platform.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime,
    ForeignKey, JSON, Index, Boolean,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def _utcnow():
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class User(Base):
    """User accounts for authentication."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="reviewer")
    country = Column(String(5), nullable=False, default="NZ")
    created_at = Column(DateTime, default=_utcnow)
    
    # Relationships
    crawl_sessions = relationship("CrawlSession", back_populates="user")
    audit_entries = relationship("AuditLog", back_populates="user")


class CrawlSession(Base):
    """Crawl configuration and execution tracking."""
    __tablename__ = "crawl_sessions"
    __table_args__ = (
        Index("ix_crawl_sessions_status", "status"),
        Index("ix_crawl_sessions_country", "country"),
        Index("ix_crawl_sessions_created_at", "created_at"),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Configuration
    country = Column(String(10), nullable=False)
    max_pages = Column(Integer, nullable=False, default=1000)
    max_minutes = Column(Integer, nullable=False, default=60)
    seed_urls = Column(JSON, nullable=False)  # List of URLs
    policy_types = Column(JSON, nullable=False)  # List of policy types
    keyword_filters = Column(JSON, nullable=False)  # List of keywords
    
    # Status tracking
    status = Column(String(50), nullable=False, default="queued")  # queued, running, completed, failed
    progress_pct = Column(Integer, default=0)
    
    # Statistics
    pages_scanned = Column(Integer, default=0)
    pdfs_found = Column(Integer, default=0)
    pdfs_downloaded = Column(Integer, default=0)
    pdfs_filtered = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    
    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="crawl_sessions")
    documents = relationship("Document", back_populates="crawl_session", cascade="all, delete-orphan")


class Document(Base):
    """Downloaded and classified policy documents."""
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_crawl_session", "crawl_session_id"),
        Index("ix_documents_country", "country"),
        Index("ix_documents_policy_type", "policy_type"),
        Index("ix_documents_classification", "classification"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_file_hash", "file_hash"),  # CRITICAL: For deduplication
        Index("ix_documents_status", "status"),  # For filtering by status
        # Compound indexes for common queries
        Index("ix_documents_country_policy_type", "country", "policy_type"),
        Index("ix_documents_crawl_status", "crawl_session_id", "status"),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Source information
    source_url = Column(Text, nullable=False)
    insurer = Column(String(255), nullable=False)
    
    # File storage (filesystem, NOT database)
    local_file_path = Column(Text, nullable=False)  # e.g., /app/storage/raw/AAInsurance/motor_pds.pdf
    file_size = Column(Integer, nullable=True)  # bytes
    file_hash = Column(String(64), nullable=True)  # SHA-256 for deduplication
    
    # Classification
    country = Column(String(10), nullable=False)
    policy_type = Column(String(100), nullable=False)
    document_type = Column(String(100), nullable=False)  # PDS, Policy Wording, Fact Sheet, etc.
    classification = Column(String(100), nullable=False)  # AI classification result
    confidence = Column(Float, nullable=False, default=0.0)
    
    # Metadata
    metadata_json = Column("metadata", JSON, nullable=True)
    warnings = Column(JSON, nullable=True)
    
    # Status
    status = Column(String(20), nullable=False, default="pending")  # pending, validated, rejected
    
    # Timestamps
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    
    # Foreign keys
    crawl_session_id = Column(Integer, ForeignKey("crawl_sessions.id", ondelete="CASCADE"), nullable=True)
    
    # Relationships
    crawl_session = relationship("CrawlSession", back_populates="documents")


class AuditLog(Base):
    """Audit trail for all system actions."""
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_created_at", "created_at"),
        Index("ix_audit_log_user_id", "user_id"),
        Index("ix_audit_log_action", "action"),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Action details
    action = Column(String(100), nullable=False)
    details = Column(JSON, nullable=True)
    
    # User context
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_name = Column(String(200), nullable=True)
    
    # Related document
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=_utcnow)
    
    # Relationships
    user = relationship("User", back_populates="audit_entries")
