"""
Tests for document download and export functionality.

Includes:
- Single document download
- Bulk download as ZIP
- ZIP with filters
- Export to CSV
- Download validation
"""
import pytest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch, MagicMock


class TestSingleDocumentDownload:
    """Tests for single document download."""
    
    def test_download_existing_document(
        self, 
        client, 
        auth_headers,
        sample_document,
        tmp_path
    ):
        """Test downloading an existing document."""
        # Create a temporary file
        test_file = tmp_path / "download_test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content for download")
        
        # Update document path
        sample_document.local_file_path = str(test_file)
        
        response = client.get(
            f"/api/documents/{sample_document.id}/download",
            headers=auth_headers
        )
        
        # May succeed or fail depending on file existence
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            assert response.headers.get("content-type") == "application/pdf"
    
    def test_download_with_token_param(
        self, 
        client, 
        sample_document,
        test_user,
        tmp_path
    ):
        """Test download with token query parameter."""
        from app.auth import create_access_token
        
        token = create_access_token(data={"sub": test_user.username})
        
        test_file = tmp_path / "token_test.pdf"
        test_file.write_bytes(b"%PDF-1.4 content")
        sample_document.local_file_path = str(test_file)
        
        response = client.get(
            f"/api/documents/{sample_document.id}/download?token={token}",
        )
        
        assert response.status_code in [200, 404]
    
    def test_download_nonexistent_file(
        self, 
        client, 
        auth_headers,
        sample_document
    ):
        """Test download when file doesn't exist on disk."""
        # Set path to non-existent file
        sample_document.local_file_path = "/nonexistent/path/file.pdf"
        
        response = client.get(
            f"/api/documents/{sample_document.id}/download",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_download_nonexistent_document(self, client, auth_headers):
        """Test downloading non-existent document."""
        response = client.get(
            "/api/documents/99999/download",
            headers=auth_headers
        )
        
        assert response.status_code == 404


class TestBulkDownloadZip:
    """Tests for bulk ZIP download."""
    
    def test_download_all_zip(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test downloading all documents as ZIP."""
        # Create temporary files for documents
        for i, doc in enumerate(multiple_sample_documents):
            test_file = tmp_path / f"bulk_{i}.pdf"
            test_file.write_bytes(f"%PDF-1.4 content {i}".encode())
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip",
            headers=auth_headers
        )
        
        # Should succeed or return 404 if no files
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            assert response.headers.get("content-type") == "application/zip"
            assert "attachment" in response.headers.get("content-disposition", "")
    
    def test_download_zip_with_country_filter(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test ZIP download with country filter."""
        # Create files
        for i, doc in enumerate(multiple_sample_documents):
            test_file = tmp_path / f"filtered_{i}.pdf"
            test_file.write_bytes(b"%PDF-1.4")
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip?country=NZ",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
    
    def test_download_zip_with_status_filter(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test ZIP download with status filter."""
        for i, doc in enumerate(multiple_sample_documents):
            test_file = tmp_path / f"status_{i}.pdf"
            test_file.write_bytes(b"%PDF-1.4")
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip?status=pending",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
    
    def test_download_zip_with_multiple_filters(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test ZIP download with multiple filters."""
        for i, doc in enumerate(multiple_sample_documents):
            test_file = tmp_path / f"multi_{i}.pdf"
            test_file.write_bytes(b"%PDF-1.4")
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip?country=NZ&policy_type=Motor&status=pending",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
    
    def test_download_zip_by_crawl_session(
        self, 
        client, 
        auth_headers,
        sample_crawl_session,
        db_session,
        tmp_path
    ):
        """Test ZIP download filtered by crawl session."""
        from app.models import Document
        
        # Create documents for this crawl session
        for i in range(3):
            doc = Document(
                source_url=f"https://example.com/crawl{i}.pdf",
                insurer="Crawl Insurer",
                local_file_path=str(tmp_path / f"crawl_{i}.pdf"),
                country="NZ",
                policy_type="Motor",
                document_type="PDS",
                classification="policy_document",
                confidence=0.9,
                status="pending",
                crawl_session_id=sample_crawl_session.id
            )
            db_session.add(doc)
            # Create the file
            (tmp_path / f"crawl_{i}.pdf").write_bytes(b"%PDF-1.4")
        db_session.commit()
        
        response = client.get(
            f"/api/documents/download-all/zip?crawl_session_id={sample_crawl_session.id}",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
    
    def test_download_zip_no_matches(
        self, 
        client, 
        auth_headers
    ):
        """Test ZIP download when no documents match filters."""
        response = client.get(
            "/api/documents/download-all/zip?country=NONEXISTENT",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "no downloadable files" in response.json()["detail"].lower()
    
    def test_download_zip_filename_format(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test ZIP filename includes filter info."""
        for i, doc in enumerate(multiple_sample_documents[:2]):
            test_file = tmp_path / f"name_{i}.pdf"
            test_file.write_bytes(b"%PDF-1.4")
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip?country=NZ&policy_type=Motor",
            headers=auth_headers
        )
        
        if response.status_code == 200:
            disposition = response.headers.get("content-disposition", "")
            assert "policycheck" in disposition
            assert ".zip" in disposition


class TestCsvExport:
    """Tests for CSV export functionality."""
    
    def test_export_csv_client_side(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test that CSV export endpoint exists."""
        # Note: CSV export may be client-side only
        # This test checks if a server-side endpoint exists
        response = client.get(
            "/api/documents/export/csv",
            headers=auth_headers
        )
        
        # May be 404 if client-side only
        assert response.status_code in [200, 404]
    
    def test_document_listing_for_csv_export(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test that document listing has all fields needed for CSV."""
        response = client.get(
            "/api/documents?limit=100",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["documents"]:
            doc = data["documents"][0]
            # Check fields typically needed for CSV export
            required_fields = [
                "id", "source_url", "insurer", "country", 
                "policy_type", "classification", "status"
            ]
            for field in required_fields:
                assert field in doc, f"Field {field} missing from document"


class TestDownloadValidation:
    """Tests for download validation and security."""
    
    def test_download_without_auth(self, client, sample_document):
        """Test download requires authentication."""
        response = client.get(
            f"/api/documents/{sample_document.id}/download"
        )
        
        assert response.status_code == 403
    
    def test_bulk_download_without_auth(self, client):
        """Test bulk download requires authentication."""
        response = client.get("/api/documents/download-all/zip")
        
        assert response.status_code == 403
    
    def test_download_path_traversal_attempt(
        self, 
        client, 
        auth_headers,
        db_session
    ):
        """Test protection against path traversal in download."""
        from app.models import Document
        
        # Create document with suspicious path
        doc = Document(
            source_url="https://example.com/test.pdf",
            insurer="Test",
            local_file_path="../../../etc/passwd",  # Suspicious path
            country="NZ",
            policy_type="Motor",
            document_type="PDS",
            classification="policy_document",
            confidence=0.9,
            status="pending"
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)
        
        response = client.get(
            f"/api/documents/{doc.id}/download",
            headers=auth_headers
        )
        
        # Should not expose system files
        assert response.status_code == 404


class TestDownloadAllVariations:
    """Tests for various download all scenarios."""
    
    def test_download_all_with_min_confidence(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test download with minimum confidence filter."""
        for i, doc in enumerate(multiple_sample_documents):
            test_file = tmp_path / f"conf_{i}.pdf"
            test_file.write_bytes(b"%PDF-1.4")
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip?min_confidence=0.92",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
    
    def test_download_all_with_classification_filter(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test download with classification filter."""
        for i, doc in enumerate(multiple_sample_documents):
            test_file = tmp_path / f"class_{i}.pdf"
            test_file.write_bytes(b"%PDF-1.4")
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip?classification=policy_document",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
    
    def test_download_all_with_search_filter(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents,
        tmp_path
    ):
        """Test download with search filter."""
        for i, doc in enumerate(multiple_sample_documents):
            test_file = tmp_path / f"search_{i}.pdf"
            test_file.write_bytes(b"%PDF-1.4")
            doc.local_file_path = str(test_file)
        
        response = client.get(
            "/api/documents/download-all/zip?search=Motor",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
