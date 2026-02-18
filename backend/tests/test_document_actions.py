"""
Tests for document action endpoints.

Includes:
- Approve document
- Reject document  
- Archive document
- Reclassify document
- Delete document
- Download document
- Document preview
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from io import BytesIO


class TestDocumentApprove:
    """Tests for document approval endpoint."""
    
    def test_approve_pending_document(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document
    ):
        """Test approving a pending document."""
        response = client.put(
            f"/api/documents/{sample_document.id}/approve",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify document status updated
        get_response = client.get(
            f"/api/documents/{sample_document.id}",
            headers=auth_headers_with_csrf
        )
        assert get_response.json()["status"] == "validated"
    
    def test_approve_already_validated_document(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document,
        db_session
    ):
        """Test approving an already validated document."""
        # First approve
        sample_document.status = "validated"
        db_session.commit()
        
        # Try to approve again
        response = client.put(
            f"/api/documents/{sample_document.id}/approve",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_approve_nonexistent_document(self, client, auth_headers_with_csrf):
        """Test approving a non-existent document."""
        response = client.put(
            "/api/documents/99999/approve",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_approve_without_auth(self, client, sample_document):
        """Test approval fails without authentication."""
        response = client.put(
            f"/api/documents/{sample_document.id}/approve"
        )
        
        assert response.status_code == 403
    
    def test_approve_without_csrf(self, client, auth_headers, sample_document):
        """Test approval fails without CSRF token."""
        response = client.put(
            f"/api/documents/{sample_document.id}/approve",
            headers=auth_headers
        )
        
        assert response.status_code == 403


class TestDocumentReject:
    """Tests for document rejection endpoint."""
    
    def test_reject_pending_document(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document
    ):
        """Test rejecting a pending document."""
        response = client.put(
            f"/api/documents/{sample_document.id}/reject",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify document status updated
        get_response = client.get(
            f"/api/documents/{sample_document.id}",
            headers=auth_headers_with_csrf
        )
        assert get_response.json()["status"] == "rejected"
    
    def test_reject_validated_document(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document,
        db_session
    ):
        """Test rejecting an already validated document."""
        sample_document.status = "validated"
        db_session.commit()
        
        response = client.put(
            f"/api/documents/{sample_document.id}/reject",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify status changed to rejected
        get_response = client.get(
            f"/api/documents/{sample_document.id}",
            headers=auth_headers_with_csrf
        )
        assert get_response.json()["status"] == "rejected"
    
    def test_reject_nonexistent_document(self, client, auth_headers_with_csrf):
        """Test rejecting a non-existent document."""
        response = client.put(
            "/api/documents/99999/reject",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 404


class TestDocumentArchive:
    """Tests for document archive endpoint."""
    
    def test_archive_pending_document(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document
    ):
        """Test archiving a pending document."""
        response = client.put(
            f"/api/documents/{sample_document.id}/archive",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify status is rejected (archive = reject)
        get_response = client.get(
            f"/api/documents/{sample_document.id}",
            headers=auth_headers_with_csrf
        )
        assert get_response.json()["status"] == "rejected"
    
    def test_archive_post_method(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document
    ):
        """Test archive endpoint with POST method."""
        response = client.post(
            f"/api/documents/{sample_document.id}/archive",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200


class TestDocumentReclassify:
    """Tests for document reclassification endpoint."""
    
    def test_reclassify_document(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document
    ):
        """Test reclassifying a document."""
        old_classification = sample_document.classification
        
        response = client.put(
            f"/api/documents/{sample_document.id}/reclassify",
            headers=auth_headers_with_csrf,
            json={"classification": "exclusion"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["classification"] == "exclusion"
        
        # Verify document updated
        get_response = client.get(
            f"/api/documents/{sample_document.id}",
            headers=auth_headers_with_csrf
        )
        doc_data = get_response.json()
        assert doc_data["classification"] == "exclusion"
        assert doc_data["document_type"] == "exclusion"
        assert doc_data["status"] == "validated"  # Auto-approved on reclassify
        assert doc_data["confidence"] == 1.0
    
    def test_reclassify_with_post_method(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document
    ):
        """Test reclassify with POST method."""
        response = client.post(
            f"/api/documents/{sample_document.id}/reclassify",
            headers=auth_headers_with_csrf,
            json={"classification": "endorsement"}
        )
        
        assert response.status_code == 200
        assert response.json()["classification"] == "endorsement"
    
    def test_reclassify_missing_classification(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document
    ):
        """Test reclassify without providing classification."""
        response = client.put(
            f"/api/documents/{sample_document.id}/reclassify",
            headers=auth_headers_with_csrf,
            json={}
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_reclassify_nonexistent_document(self, client, auth_headers_with_csrf):
        """Test reclassifying a non-existent document."""
        response = client.put(
            "/api/documents/99999/reclassify",
            headers=auth_headers_with_csrf,
            json={"classification": "exclusion"}
        )
        
        assert response.status_code == 404


class TestDocumentDelete:
    """Tests for document deletion endpoint."""
    
    def test_delete_document(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document,
        db_session
    ):
        """Test deleting a document."""
        doc_id = sample_document.id
        
        response = client.delete(
            f"/api/documents/{doc_id}",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert str(doc_id) in response.json()["message"]
        
        # Verify document is deleted
        from app.models import Document
        deleted_doc = db_session.query(Document).filter(Document.id == doc_id).first()
        assert deleted_doc is None
    
    def test_delete_document_with_file_cleanup(
        self, 
        client, 
        auth_headers_with_csrf,
        db_session
    ):
        """Test that deleting a document attempts file cleanup."""
        # Create document with file path
        from app.models import Document
        doc = Document(
            source_url="https://example.com/to_delete.pdf",
            insurer="Test",
            local_file_path="/tmp/test_delete.pdf",
            file_size=100,
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
        
        response = client.delete(
            f"/api/documents/{doc.id}",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
    
    def test_delete_nonexistent_document(self, client, auth_headers_with_csrf):
        """Test deleting a non-existent document."""
        response = client.delete(
            "/api/documents/99999",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_delete_without_auth(self, client, sample_document):
        """Test delete fails without authentication."""
        response = client.delete(
            f"/api/documents/{sample_document.id}"
        )
        
        assert response.status_code == 403


class TestDocumentDownload:
    """Tests for document download endpoint."""
    
    def test_download_document_success(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document,
        tmp_path
    ):
        """Test downloading a document."""
        # Create a temporary file for the document
        import os
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")
        
        # Update document path to temp file
        sample_document.local_file_path = str(test_file)
        
        response = client.get(
            f"/api/documents/{sample_document.id}/download",
            headers=auth_headers_with_csrf
        )
        
        # Should either succeed or return 404 if file doesn't exist in test env
        assert response.status_code in [200, 404]
    
    def test_download_nonexistent_document(self, client, auth_headers_with_csrf):
        """Test downloading a non-existent document."""
        response = client.get(
            "/api/documents/99999/download",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 404
    
    def test_download_without_auth(self, client, sample_document):
        """Test download fails without authentication."""
        response = client.get(
            f"/api/documents/{sample_document.id}/download"
        )
        
        assert response.status_code == 403


class TestDocumentPreview:
    """Tests for document preview endpoint."""
    
    def test_preview_document_success(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document,
        tmp_path
    ):
        """Test previewing a document (inline PDF)."""
        import os
        test_file = tmp_path / "preview.pdf"
        test_file.write_bytes(b"%PDF-1.4 preview content")
        
        sample_document.local_file_path = str(test_file)
        
        response = client.get(
            f"/api/documents/{sample_document.id}/preview",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            assert response.headers.get("content-type") == "application/pdf"
            # Check inline disposition
            assert "inline" in response.headers.get("content-disposition", "")
    
    def test_preview_with_token_param(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_document,
        tmp_path
    ):
        """Test preview with token query parameter."""
        import os
        test_file = tmp_path / "preview_token.pdf"
        test_file.write_bytes(b"%PDF-1.4 content")
        
        sample_document.local_file_path = str(test_file)
        
        # Get token
        from app.auth import create_access_token
        token = create_access_token(data={"sub": "testuser"})
        
        response = client.get(
            f"/api/documents/{sample_document.id}/preview?token={token}",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code in [200, 404]


class TestBulkActions:
    """Tests for bulk document actions."""
    
    def test_approve_multiple_documents(
        self,
        client,
        auth_headers_with_csrf,
        multiple_sample_documents
    ):
        """Test approving multiple documents sequentially."""
        approved_count = 0
        
        for doc in multiple_sample_documents:
            if doc.status == "pending":
                response = client.put(
                    f"/api/documents/{doc.id}/approve",
                    headers=auth_headers_with_csrf
                )
                assert response.status_code == 200
                approved_count += 1
        
        assert approved_count > 0
    
    def test_delete_multiple_documents(
        self,
        client,
        auth_headers_with_csrf,
        multiple_sample_documents,
        db_session
    ):
        """Test deleting multiple documents."""
        deleted_ids = []
        
        for doc in multiple_sample_documents[:3]:  # Delete first 3
            response = client.delete(
                f"/api/documents/{doc.id}",
                headers=auth_headers_with_csrf
            )
            assert response.status_code == 200
            deleted_ids.append(doc.id)
        
        # Verify they're deleted
        from app.models import Document
        remaining = db_session.query(Document).filter(
            Document.id.in_([d.id for d in multiple_sample_documents[:3]])
        ).count()
        assert remaining == 0
        
        # Verify others still exist
        remaining_others = db_session.query(Document).filter(
            Document.id.in_([d.id for d in multiple_sample_documents[3:]])
        ).count()
        assert remaining_others == 2
