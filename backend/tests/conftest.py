"""
Pytest fixtures and configuration for PolicyCheck tests.

This module provides:
- Test database setup with SQLite in-memory
- Test client with overridden dependencies
- Authentication fixtures
- Sample data fixtures
"""
import os
import sys

# CRITICAL: Set environment variables BEFORE any app imports
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "testing"
os.environ["CACHE_ENABLED"] = "false"
os.environ["METRICS_ENABLED"] = "false"
os.environ["API_RATE_LIMIT_ENABLED"] = "false"

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone
from typing import Generator, Dict, Any
from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

# Now import app components (after env vars are set)
from app.main import app
from app.database import get_db
from app.models import Base
from app.auth import create_access_token, get_password_hash
from app.models import User, Document, CrawlSession, AuditLog

# ============================================================================
# TEST DATABASE CONFIGURATION
# ============================================================================

TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def db_engine():
    """Create a database engine for testing (session scope)."""
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine
    # Drop all tables after tests
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    # Enable foreign key constraints for SQLite
    session.execute(text("PRAGMA foreign_keys=ON"))
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session) -> Generator[TestClient, None, None]:
    """Create a test client with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================

@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        username="testuser",
        password_hash=get_password_hash("TestPass123!"),
        name="Test User",
        role="reviewer",
        country="NZ",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create an admin test user."""
    user = User(
        username="adminuser",
        password_hash=get_password_hash("AdminPass123!"),
        name="Admin User",
        role="admin",
        country="NZ",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> Dict[str, str]:
    """Get authentication headers for test user."""
    token = create_access_token(data={"sub": test_user.username, "user_id": test_user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers(admin_user: User) -> Dict[str, str]:
    """Get authentication headers for admin user."""
    token = create_access_token(data={"sub": admin_user.username, "user_id": admin_user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_with_csrf(auth_headers: Dict[str, str]) -> Dict[str, str]:
    """Get authentication headers with CSRF token."""
    from app.auth import create_csrf_token
    headers = auth_headers.copy()
    headers["X-CSRF-Token"] = create_csrf_token(subject="testuser")
    return headers


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_document(db_session: Session, test_user: User) -> Document:
    """Create a sample document for testing."""
    doc = Document(
        source_url="https://example.com/test.pdf",
        insurer="Test Insurer",
        local_file_path="/app/storage/raw/Test_Insurer/test.pdf",
        file_size=1024,
        file_hash="abc123hash",
        country="NZ",
        policy_type="Motor",
        document_type="PDS",
        classification="policy_document",
        confidence=0.95,
        status="pending",
        metadata_json={"pages": 10, "version": "1.0"},
        warnings=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


@pytest.fixture
def multiple_sample_documents(db_session: Session, test_user: User) -> list[Document]:
    """Create multiple sample documents for testing."""
    docs = []
    for i in range(5):
        doc = Document(
            source_url=f"https://example.com/test{i}.pdf",
            insurer=f"Test Insurer {i}",
            local_file_path=f"/app/storage/raw/Test_Insurer_{i}/test{i}.pdf",
            file_size=1024 * (i + 1),
            file_hash=f"hash_{i}",
            country="NZ" if i % 2 == 0 else "AU",
            policy_type="Motor" if i % 2 == 0 else "Home",
            document_type="PDS",
            classification="policy_document",
            confidence=0.9 + (i * 0.01),
            status=["pending", "validated", "rejected"][i % 3],
            metadata_json={"pages": 10 + i},
            warnings=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(doc)
        docs.append(doc)
    db_session.commit()
    for doc in docs:
        db_session.refresh(doc)
    return docs


@pytest.fixture
def sample_crawl_session(db_session: Session, test_user: User) -> CrawlSession:
    """Create a sample crawl session."""
    session = CrawlSession(
        country="NZ",
        max_pages=100,
        max_minutes=30,
        seed_urls=["https://example.com"],
        policy_types=["Motor"],
        keyword_filters=[],
        status="completed",
        progress_pct=100,
        pages_scanned=50,
        pdfs_found=10,
        pdfs_downloaded=8,
        pdfs_filtered=2,
        errors_count=0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        user_id=test_user.id,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


# ============================================================================
# FILE UPLOAD FIXTURES
# ============================================================================

@pytest.fixture
def sample_pdf_file() -> tuple[str, BytesIO, str]:
    """Create a sample PDF file for upload testing."""
    # Minimal valid PDF content
    pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n196\n%%EOF"
    return ("test_document.pdf", BytesIO(pdf_content), "application/pdf")


@pytest.fixture
def multiple_sample_pdf_files() -> list[tuple[str, BytesIO, str]]:
    """Create multiple sample PDF files for batch upload testing."""
    files = []
    for i in range(3):
        pdf_content = f"%PDF-1.4\n%Test PDF {i}\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF".encode()
        files.append((f"test_document_{i}.pdf", BytesIO(pdf_content), "application/pdf"))
    return files


@pytest.fixture
def invalid_file() -> tuple[str, BytesIO, str]:
    """Create an invalid (non-PDF) file for testing."""
    content = b"This is not a PDF file, just some text content."
    return ("test_document.txt", BytesIO(content), "text/plain")


# ============================================================================
# UTILITY FIXTURES
# ============================================================================

@pytest.fixture
def api_base_url() -> str:
    """Base URL for API endpoints."""
    return "/api"


@pytest.fixture
def api_v1_base_url() -> str:
    """Base URL for API v1 endpoints."""
    return "/api/v1"


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test name/pattern."""
    for item in items:
        # Auto-mark tests based on name patterns
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)
        elif "unit" in item.nodeid.lower():
            item.add_marker(pytest.mark.unit)
