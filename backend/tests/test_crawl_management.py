"""
Tests for crawl management endpoints.

Includes:
- Start crawl
- Get crawl status
- Get crawl results
- List crawl sessions
- Delete crawl
- Get crawl logs
- Seed URL discovery
- Custom insurer management
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestStartCrawl:
    """Tests for starting crawl sessions."""
    
    def test_start_crawl_success(
        self, 
        client, 
        auth_headers_with_csrf, 
        test_user,
        db_session
    ):
        """Test starting a new crawl session."""
        with patch('app.routers.crawl_router.crawl_service') as mock_service:
            # Mock the service methods
            mock_service.can_start_crawl.return_value = (True, "")
            mock_session = MagicMock()
            mock_session.id = 1
            mock_session.status = "running"
            mock_service.create_crawl_session.return_value = mock_session
            mock_service.get_active_crawl_count.return_value = 1
            
            response = client.post(
                "/api/crawl/start",
                headers=auth_headers_with_csrf,
                json={
                    "country": "NZ",
                    "max_pages": 100,
                    "max_minutes": 30,
                    "seed_urls": ["https://example.com/insurance"],
                    "policy_types": ["Motor"],
                    "keyword_filters": []
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["crawl_id"] == 1
            assert data["status"] == "running"
            assert "message" in data
    
    def test_start_crawl_root_endpoint(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test starting crawl via root /api/crawl endpoint."""
        with patch('app.routers.crawl_router.crawl_service') as mock_service:
            mock_service.can_start_crawl.return_value = (True, "")
            mock_session = MagicMock()
            mock_session.id = 2
            mock_session.status = "running"
            mock_service.create_crawl_session.return_value = mock_session
            mock_service.get_active_crawl_count.return_value = 1
            
            response = client.post(
                "/api/crawl",
                headers=auth_headers_with_csrf,
                json={
                    "country": "AU",
                    "max_pages": 50,
                    "max_minutes": 20,
                    "seed_urls": ["https://example.com/au"],
                    "policy_types": [],
                    "keyword_filters": []
                }
            )
            
            assert response.status_code == 200
            assert response.json()["crawl_id"] == 2
    
    def test_start_crawl_at_capacity(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test starting crawl when at max concurrent capacity."""
        with patch('app.routers.crawl_router.crawl_service') as mock_service:
            mock_service.can_start_crawl.return_value = (
                False, 
                "Maximum concurrent crawls reached"
            )
            mock_service.get_active_crawl_count.return_value = 3
            mock_service.MAX_CONCURRENT_CRAWLS = 3
            
            response = client.post(
                "/api/crawl/start",
                headers=auth_headers_with_csrf,
                json={
                    "country": "NZ",
                    "max_pages": 100,
                    "max_minutes": 30,
                    "seed_urls": ["https://example.com"],
                    "policy_types": [],
                    "keyword_filters": []
                }
            )
            
            assert response.status_code == 429  # Too Many Requests
            assert "concurrent" in response.json()["detail"]["error"].lower()
    
    def test_start_crawl_invalid_url(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test starting crawl with invalid seed URL."""
        response = client.post(
            "/api/crawl/start",
            headers=auth_headers_with_csrf,
            json={
                "country": "NZ",
                "max_pages": 100,
                "max_minutes": 30,
                "seed_urls": ["not-a-valid-url"],  # Invalid URL
                "policy_types": [],
                "keyword_filters": []
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_start_crawl_without_auth(self, client):
        """Test starting crawl without authentication."""
        response = client.post(
            "/api/crawl/start",
            json={
                "country": "NZ",
                "max_pages": 100,
                "max_minutes": 30,
                "seed_urls": ["https://example.com"],
            }
        )
        
        assert response.status_code == 403
    
    def test_start_crawl_max_pages_validation(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test max_pages validation limits."""
        # Test max_pages too high
        response = client.post(
            "/api/crawl/start",
            headers=auth_headers_with_csrf,
            json={
                "country": "NZ",
                "max_pages": 1000000,  # Exceeds limit
                "max_minutes": 30,
                "seed_urls": ["https://example.com"],
            }
        )
        
        assert response.status_code == 422
        
        # Test max_pages too low
        response = client.post(
            "/api/crawl/start",
            headers=auth_headers_with_csrf,
            json={
                "country": "NZ",
                "max_pages": 0,  # Below minimum
                "max_minutes": 30,
                "seed_urls": ["https://example.com"],
            }
        )
        
        assert response.status_code == 422


class TestGetCrawlStatus:
    """Tests for getting crawl status."""
    
    def test_get_crawl_status_success(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session
    ):
        """Test getting status of an existing crawl."""
        response = client.get(
            f"/api/crawl/{sample_crawl_session.id}/status",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_crawl_session.id
        assert data["status"] == sample_crawl_session.status
        assert "progress_pct" in data
        assert "pages_scanned" in data
    
    def test_get_crawl_status_nonexistent(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test getting status of non-existent crawl."""
        response = client.get(
            "/api/crawl/99999/status",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 404
    
    def test_get_crawl_status_derived_phases(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session,
        db_session
    ):
        """Test that current_phase is correctly derived from progress."""
        test_cases = [
            (10, "running", "Scanning"),  # progress < 50
            (75, "running", "Downloading"),  # 50 <= progress < 100
            (100, "completed", "Complete"),
        ]
        
        for progress, status, expected_phase in test_cases:
            sample_crawl_session.progress_pct = progress
            sample_crawl_session.status = status
            sample_crawl_session.pdfs_found = 10
            sample_crawl_session.pdfs_downloaded = 8
            sample_crawl_session.pages_scanned = 50
            db_session.commit()
            
            response = client.get(
                f"/api/crawl/{sample_crawl_session.id}/status",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            assert response.json()["current_phase"] == expected_phase


class TestGetCrawlResults:
    """Tests for getting crawl results."""
    
    def test_get_crawl_results_success(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session,
        db_session
    ):
        """Test getting documents from a crawl session."""
        # Add some documents to the crawl session
        from app.models import Document
        for i in range(3):
            doc = Document(
                source_url=f"https://example.com/doc{i}.pdf",
                insurer=f"Insurer {i}",
                local_file_path=f"/path/doc{i}.pdf",
                country="NZ",
                policy_type="Motor",
                document_type="PDS",
                classification="policy_document",
                confidence=0.9,
                status="pending",
                crawl_session_id=sample_crawl_session.id
            )
            db_session.add(doc)
        db_session.commit()
        
        response = client.get(
            f"/api/crawl/{sample_crawl_session.id}/results",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["crawl_id"] == sample_crawl_session.id
        assert data["total"] == 3
        assert len(data["documents"]) == 3
    
    def test_get_crawl_results_empty(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session
    ):
        """Test getting results for crawl with no documents."""
        response = client.get(
            f"/api/crawl/{sample_crawl_session.id}/results",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["documents"] == []


class TestListCrawlSessions:
    """Tests for listing crawl sessions."""
    
    def test_list_crawl_sessions(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session,
        test_user,
        db_session
    ):
        """Test listing user's crawl sessions."""
        response = client.get(
            "/api/crawl/sessions",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # First item should be the most recent
        assert data[0]["id"] == sample_crawl_session.id
    
    def test_list_crawl_sessions_pagination(
        self, 
        client, 
        auth_headers_with_csrf, 
        test_user,
        db_session
    ):
        """Test crawl sessions pagination."""
        # Create multiple crawl sessions
        from app.models import CrawlSession
        for i in range(5):
            session = CrawlSession(
                country="NZ",
                max_pages=100,
                max_minutes=30,
                seed_urls=["https://example.com"],
                policy_types=[],
                keyword_filters=[],
                status="completed",
                user_id=test_user.id,
                created_at=datetime.now(timezone.utc)
            )
            db_session.add(session)
        db_session.commit()
        
        response = client.get(
            "/api/crawl/sessions?limit=3&offset=0",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        
        # Get next page
        response = client.get(
            "/api/crawl/sessions?limit=3&offset=3",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2  # At least 2 more


class TestDeleteCrawl:
    """Tests for deleting crawl sessions."""
    
    def test_delete_crawl_success(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session,
        db_session
    ):
        """Test deleting a completed crawl session."""
        crawl_id = sample_crawl_session.id
        
        response = client.delete(
            f"/api/crawl/{crawl_id}",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["crawl_id"] == crawl_id
    
    def test_delete_running_crawl_fails(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session,
        db_session
    ):
        """Test that deleting a running crawl fails."""
        sample_crawl_session.status = "running"
        db_session.commit()
        
        response = client.delete(
            f"/api/crawl/{sample_crawl_session.id}",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 409  # Conflict
        assert "running" in response.json()["detail"].lower()
    
    def test_delete_nonexistent_crawl(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test deleting a non-existent crawl."""
        response = client.delete(
            "/api/crawl/99999",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 404
    
    def test_delete_crawl_cascades_to_documents(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session,
        db_session
    ):
        """Test that deleting crawl removes associated documents."""
        from app.models import Document
        
        # Add documents to crawl
        for i in range(3):
            doc = Document(
                source_url=f"https://example.com/doc{i}.pdf",
                insurer="Test",
                local_file_path=f"/path/doc{i}.pdf",
                country="NZ",
                policy_type="Motor",
                document_type="PDS",
                classification="policy_document",
                confidence=0.9,
                status="pending",
                crawl_session_id=sample_crawl_session.id
            )
            db_session.add(doc)
        db_session.commit()
        
        crawl_id = sample_crawl_session.id
        
        response = client.delete(
            f"/api/crawl/{crawl_id}",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        
        # Verify documents are deleted
        remaining = db_session.query(Document).filter(
            Document.crawl_session_id == crawl_id
        ).count()
        assert remaining == 0


class TestGetCrawlLogs:
    """Tests for crawl log endpoint."""
    
    def test_get_crawl_logs(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session
    ):
        """Test getting crawl logs."""
        with patch('app.routers.crawl_router.crawl_service') as mock_service:
            mock_service.get_crawl_logs.return_value = [
                {"level": "INFO", "message": "Started crawl"},
                {"level": "INFO", "message": "Found 10 PDFs"},
            ]
            
            response = client.get(
                f"/api/crawl/{sample_crawl_session.id}/logs",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["crawl_id"] == sample_crawl_session.id
            assert "entries" in data
    
    def test_get_crawl_logs_with_since_param(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session
    ):
        """Test getting crawl logs with since parameter."""
        with patch('app.routers.crawl_router.crawl_service') as mock_service:
            mock_service.get_crawl_logs.return_value = [
                {"level": "INFO", "message": "New log entry"},
            ]
            
            response = client.get(
                f"/api/crawl/{sample_crawl_session.id}/logs?since=5",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            mock_service.get_crawl_logs.assert_called_with(sample_crawl_session.id, since=5)


class TestGetLatestCrawl:
    """Tests for latest crawl endpoint."""
    
    def test_get_latest_crawl(
        self, 
        client, 
        auth_headers_with_csrf, 
        sample_crawl_session
    ):
        """Test getting the latest crawl session."""
        response = client.get(
            "/api/crawl/latest",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["crawl"] is not None
        assert data["crawl"]["id"] == sample_crawl_session.id
    
    def test_get_latest_crawl_no_crawls(
        self, 
        client, 
        auth_headers_with_csrf,
        db_session
    ):
        """Test getting latest when user has no crawls."""
        # Delete all crawls
        from app.models import CrawlSession
        db_session.query(CrawlSession).delete()
        db_session.commit()
        
        response = client.get(
            "/api/crawl/latest",
            headers=auth_headers_with_csrf
        )
        
        assert response.status_code == 200
        assert response.json()["crawl"] is None


class TestActiveCrawlCount:
    """Tests for active crawl count endpoint."""
    
    def test_get_active_crawl_count(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test getting active crawl count."""
        with patch('app.routers.crawl_router.crawl_service') as mock_service:
            mock_service.get_active_crawl_count.return_value = 2
            mock_service.MAX_CONCURRENT_CRAWLS = 3
            
            response = client.get(
                "/api/crawl/active/count",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["active_crawls"] == 2
            assert data["max_concurrent_crawls"] == 3
            assert data["available_slots"] == 1
            assert data["at_capacity"] == False


class TestSeedUrls:
    """Tests for seed URL discovery endpoints."""
    
    def test_get_seed_urls(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test getting seed URLs for a country."""
        with patch('app.routers.crawl_router.seed_url_service') as mock_service:
            mock_service.get_seed_urls.return_value = [
                {
                    "insurer": "Test Insurance",
                    "seed_urls": ["https://test.com/policies"],
                    "policy_types": ["Motor", "Home"]
                }
            ]
            
            response = client.get(
                "/api/crawl/seed-urls?country=NZ",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["country"] == "NZ"
            assert "insurers" in data
            assert len(data["insurers"]) == 1
    
    def test_get_seed_urls_with_filters(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test getting seed URLs with policy type and insurer filters."""
        with patch('app.routers.crawl_router.seed_url_service') as mock_service:
            mock_service.get_seed_urls.return_value = []
            
            response = client.get(
                "/api/crawl/seed-urls?country=AU&policy_type=Motor&insurer=Test",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            mock_service.get_seed_urls.assert_called_with(
                country="AU",
                policy_type="Motor",
                insurer="Test",
                validate=False
            )
    
    def test_get_supported_countries(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test getting list of supported countries."""
        with patch('app.routers.crawl_router.seed_url_service') as mock_service:
            mock_service.get_supported_countries.return_value = [
                {"code": "NZ", "name": "New Zealand"},
                {"code": "AU", "name": "Australia"},
            ]
            
            response = client.get(
                "/api/crawl/seed-urls/countries",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            assert "countries" in response.json()


class TestCustomInsurers:
    """Tests for custom insurer management."""
    
    def test_add_custom_insurer(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test adding a custom insurer."""
        with patch('app.routers.crawl_router.seed_url_service') as mock_service:
            mock_service.add_custom_insurer.return_value = {
                "country": "NZ",
                "insurer": "Custom Insurance Co",
                "seed_urls": ["https://custom.com"]
            }
            
            response = client.post(
                "/api/crawl/custom-insurers",
                headers=auth_headers_with_csrf,
                json={
                    "country": "NZ",
                    "insurer_name": "Custom Insurance Co",
                    "seed_urls": ["https://custom.com/policies"],
                    "policy_types": ["Motor"]
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "Custom Insurance Co" in data["message"]
    
    def test_add_custom_insurer_invalid_url(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test adding custom insurer with invalid URL."""
        response = client.post(
            "/api/crawl/custom-insurers",
            headers=auth_headers_with_csrf,
            json={
                "country": "NZ",
                "insurer_name": "Bad Insurer",
                "seed_urls": ["not-a-url"],
            }
        )
        
        assert response.status_code == 422
    
    def test_remove_custom_insurer(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test removing a custom insurer."""
        with patch('app.routers.crawl_router.seed_url_service') as mock_service:
            mock_service.remove_custom_insurer.return_value = True
            
            response = client.delete(
                "/api/crawl/custom-insurers/NZ/Custom%20Insurance",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            assert "removed" in response.json()["message"].lower()
    
    def test_remove_nonexistent_insurer(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test removing a non-existent custom insurer."""
        with patch('app.routers.crawl_router.seed_url_service') as mock_service:
            mock_service.remove_custom_insurer.return_value = False
            
            response = client.delete(
                "/api/crawl/custom-insurers/NZ/NonExistent",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 404
    
    def test_list_custom_insurers(
        self, 
        client, 
        auth_headers_with_csrf
    ):
        """Test listing custom insurers."""
        with patch('app.routers.crawl_router.seed_url_service') as mock_service:
            mock_service.list_custom_insurers.return_value = [
                {"country": "NZ", "insurer": "Custom Co", "seed_urls": []}
            ]
            
            response = client.get(
                "/api/crawl/custom-insurers",
                headers=auth_headers_with_csrf
            )
            
            assert response.status_code == 200
            assert isinstance(response.json(), list)
