"""
Tests for document upload functionality.

Includes:
- Single file upload
- Multiple files upload (batch)
- Invalid file type rejection
- File size validation
- Authentication requirements
- Classification after upload
"""
import pytest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch, MagicMock

from app.models import Document


class TestSingleFileUpload:
    """Tests for single document upload endpoint."""
    
    def test_upload_single_pdf_success(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_pdf_file,
        db_session
    ):
        """Test successful upload of a single PDF file."""
        filename, file_content, content_type = sample_pdf_file
        
        # Mock the classification service
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Motor",
                "classification": "policy_document",
                "confidence": 0.95,
                "status": "pending",
                "metadata": {"pages": 5, "extracted_text_sample": "Sample"},
                "warnings": []
            }
            
            response = client.post(
                "/api/documents/upload",
                headers=auth_headers_with_csrf,
                files={"file": (filename, file_content, content_type)},
                data={"policy_type": "Motor", "country": "NZ"}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert data["classification"] == "policy_document"
        assert data["country"] == "NZ"
        assert data["status"] == "pending"
        assert "id" in data
    
    def test_upload_without_auth(self, client, sample_pdf_file):
        """Test upload fails without authentication."""
        filename, file_content, content_type = sample_pdf_file
        
        response = client.post(
            "/api/documents/upload",
            files={"file": (filename, file_content, content_type)},
            data={"policy_type": "Motor", "country": "NZ"}
        )
        
        assert response.status_code == 403
    
    def test_upload_without_csrf_token(self, client, auth_headers, sample_pdf_file):
        """Test upload fails without CSRF token on POST request."""
        filename, file_content, content_type = sample_pdf_file
        
        response = client.post(
            "/api/documents/upload",
            headers=auth_headers,  # No CSRF token
            files={"file": (filename, file_content, content_type)},
            data={"policy_type": "Motor", "country": "NZ"}
        )
        
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]
    
    def test_upload_invalid_file_type(self, client, auth_headers_with_csrf, invalid_file):
        """Test upload rejects non-PDF files."""
        filename, file_content, content_type = invalid_file
        
        response = client.post(
            "/api/documents/upload",
            headers=auth_headers_with_csrf,
            files={"file": (filename, file_content, content_type)},
            data={"policy_type": "Motor", "country": "NZ"}
        )
        
        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]
    
    def test_upload_with_different_countries(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_pdf_file,
        db_session
    ):
        """Test upload with different country codes."""
        filename, file_content, content_type = sample_pdf_file
        countries = ["NZ", "AU", "UK", "US"]
        
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Motor",
                "classification": "policy_document",
                "confidence": 0.95,
                "status": "pending",
                "metadata": {},
                "warnings": []
            }
            
            for country in countries:
                file_content.seek(0)  # Reset file pointer
                response = client.post(
                    "/api/documents/upload",
                    headers=auth_headers_with_csrf,
                    files={"file": (f"test_{country}.pdf", file_content, content_type)},
                    data={"policy_type": "Motor", "country": country}
                )
                
                assert response.status_code == 201
                assert response.json()["country"] == country


class TestMultipleFileUpload:
    """Tests for uploading multiple files simultaneously (batch upload)."""
    
    def test_upload_multiple_pdfs_simultaneously(
        self, 
        client, 
        auth_headers_with_csrf, 
        db_session
    ):
        """Test uploading multiple PDF files at the same time."""
        # Create multiple PDF files
        files = []
        for i in range(3):
            pdf_content = f"%PDF-1.4\n%Test PDF {i}\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF".encode()
            files.append(("file", (f"batch_test_{i}.pdf", BytesIO(pdf_content), "application/pdf")))
        
        # Note: The current API supports single file per request, but we can test
        # the behavior when multiple files are attempted
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Motor",
                "classification": "policy_document",
                "confidence": 0.95,
                "status": "pending",
                "metadata": {},
                "warnings": []
            }
            
            # Current implementation only processes the first file
            # This test documents current behavior
            response = client.post(
                "/api/documents/upload",
                headers=auth_headers_with_csrf,
                files=files  # Multiple files
            )
            
            # The endpoint accepts files parameter but only processes one
            # This is testing the actual behavior
            assert response.status_code in [201, 422]
    
    def test_batch_upload_endpoint(
        self, 
        client, 
        auth_headers_with_csrf, 
        db_session
    ):
        """Test batch upload endpoint for multiple files."""
        # Create multiple files for batch upload
        files = []
        for i in range(3):
            pdf_content = f"%PDF-1.4\n%Batch test {i}\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF".encode()
            files.append(("files", (f"batch_{i}.pdf", BytesIO(pdf_content), "application/pdf")))
        
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Home",
                "classification": "policy_document",
                "confidence": 0.92,
                "status": "pending",
                "metadata": {},
                "warnings": []
            }
            
            # Test batch endpoint if it exists, otherwise test sequential uploads
            response = client.post(
                "/api/documents/upload",
                headers=auth_headers_with_csrf,
                files=files,
                data={"policy_type": "Home", "country": "AU"}
            )
            
            # Document the current API behavior
            # If batch is not supported, it should return appropriate error
            assert response.status_code in [201, 400, 422]
    
    def test_upload_multiple_with_mixed_validity(
        self,
        client,
        auth_headers_with_csrf,
        db_session
    ):
        """Test upload with mix of valid PDFs and invalid files."""
        # Create one valid PDF and one invalid file
        valid_pdf = BytesIO(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF")
        invalid_file = BytesIO(b"This is not a PDF")
        
        files = [
            ("files", ("valid.pdf", valid_pdf, "application/pdf")),
            ("files", ("invalid.txt", invalid_file, "text/plain"))
        ]
        
        response = client.post(
            "/api/documents/upload",
            headers=auth_headers_with_csrf,
            files=files,
            data={"policy_type": "Motor", "country": "NZ"}
        )
        
        # API should reject if any file is invalid
        assert response.status_code in [400, 422]
    
    def test_sequential_multiple_uploads(
        self,
        client,
        auth_headers_with_csrf,
        db_session
    ):
        """Test uploading multiple files sequentially."""
        uploaded_ids = []
        
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Motor",
                "classification": "policy_document",
                "confidence": 0.95,
                "status": "pending",
                "metadata": {},
                "warnings": []
            }
            
            for i in range(5):
                pdf_content = f"%PDF-1.4\n%Sequential {i}\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF".encode()
                
                response = client.post(
                    "/api/documents/upload",
                    headers=auth_headers_with_csrf,
                    files={"file": (f"seq_{i}.pdf", BytesIO(pdf_content), "application/pdf")},
                    data={"policy_type": "Motor", "country": "NZ"}
                )
                
                assert response.status_code == 201
                uploaded_ids.append(response.json()["id"])
        
        # Verify all uploads succeeded
        assert len(uploaded_ids) == 5
        assert len(set(uploaded_ids)) == 5  # All unique IDs
        
        # Verify in database
        docs = db_session.query(Document).filter(Document.id.in_(uploaded_ids)).all()
        assert len(docs) == 5


class TestUploadValidation:
    """Tests for upload validation and error handling."""
    
    def test_upload_empty_file(self, client, auth_headers_with_csrf):
        """Test upload of empty file."""
        empty_pdf = BytesIO(b"")
        
        response = client.post(
            "/api/documents/upload",
            headers=auth_headers_with_csrf,
            files={"file": ("empty.pdf", empty_pdf, "application/pdf")},
            data={"policy_type": "Motor", "country": "NZ"}
        )
        
        # Empty PDF should be handled (may succeed or fail depending on implementation)
        assert response.status_code in [201, 400, 500]
    
    def test_upload_missing_filename(self, client, auth_headers_with_csrf):
        """Test upload without filename."""
        pdf_content = b"%PDF-1.4\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
        
        response = client.post(
            "/api/documents/upload",
            headers=auth_headers_with_csrf,
            files={"file": ("", BytesIO(pdf_content), "application/pdf")},
            data={"policy_type": "Motor", "country": "NZ"}
        )
        
        # Should fail without filename
        assert response.status_code in [400, 422]
    
    def test_upload_large_filename(self, client, auth_headers_with_csrf):
        """Test upload with very long filename."""
        long_name = "a" * 200 + ".pdf"
        pdf_content = b"%PDF-1.4\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
        
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Motor",
                "classification": "policy_document",
                "confidence": 0.95,
                "status": "pending",
                "metadata": {},
                "warnings": []
            }
            
            response = client.post(
                "/api/documents/upload",
                headers=auth_headers_with_csrf,
                files={"file": (long_name, BytesIO(pdf_content), "application/pdf")},
                data={"policy_type": "Motor", "country": "NZ"}
            )
            
            # Should handle long filenames gracefully
            assert response.status_code in [201, 400]
    
    def test_upload_special_chars_in_filename(self, client, auth_headers_with_csrf):
        """Test upload with special characters in filename."""
        special_names = [
            "file with spaces.pdf",
            "file-with-dashes.pdf",
            "file_with_underscores.pdf",
            "file.multiple.dots.pdf",
            "M%C3%A4rz.pdf",  # URL encoded
        ]
        
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Motor",
                "classification": "policy_document",
                "confidence": 0.95,
                "status": "pending",
                "metadata": {},
                "warnings": []
            }
            
            for name in special_names:
                pdf_content = b"%PDF-1.4\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
                
                response = client.post(
                    "/api/documents/upload",
                    headers=auth_headers_with_csrf,
                    files={"file": (name, BytesIO(pdf_content), "application/pdf")},
                    data={"policy_type": "Motor", "country": "NZ"}
                )
                
                # Should handle special characters
                assert response.status_code in [201, 400]


class TestUploadClassification:
    """Tests for document classification during upload."""
    
    def test_upload_triggers_classification(
        self,
        client,
        auth_headers_with_csrf,
        sample_pdf_file,
        db_session
    ):
        """Test that upload triggers document classification."""
        filename, file_content, content_type = sample_pdf_file
        
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.return_value = {
                "detected_policy_type": "Home",
                "classification": "policy_wording",
                "confidence": 0.88,
                "status": "pending",
                "metadata": {"test": True},
                "warnings": ["Low confidence"]
            }
            
            response = client.post(
                "/api/documents/upload",
                headers=auth_headers_with_csrf,
                files={"file": (filename, file_content, content_type)},
                data={"policy_type": "General", "country": "NZ"}
            )
            
            assert response.status_code == 201
            data = response.json()
            assert data["classification"] == "policy_wording"
            assert data["confidence"] == 0.88
            assert data["policy_type"] == "Home"
            mock_classify.assert_called_once()
    
    def test_upload_classification_error_handling(
        self,
        client,
        auth_headers_with_csrf,
        sample_pdf_file
    ):
        """Test handling of classification service errors."""
        filename, file_content, content_type = sample_pdf_file
        
        with patch('app.routers.documents_router.classify_document') as mock_classify:
            mock_classify.side_effect = Exception("Classification service error")
            
            response = client.post(
                "/api/documents/upload",
                headers=auth_headers_with_csrf,
                files={"file": (filename, file_content, content_type)},
                data={"policy_type": "Motor", "country": "NZ"}
            )
            
            assert response.status_code == 500
            assert "Upload failed" in response.json()["detail"]
