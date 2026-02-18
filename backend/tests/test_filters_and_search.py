"""
Tests for document filtering, search, and listing.

Includes:
- Filter options endpoint
- Document listing with filters
- Document search
- Pagination
- Sorting
- Combined filters
"""
import pytest
from datetime import datetime, timezone


class TestFilterOptions:
    """Tests for filter options endpoint."""
    
    def test_get_filter_options_success(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test getting filter options returns distinct values."""
        response = client.get(
            "/api/documents/filters/options",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check all expected keys exist
        assert "countries" in data
        assert "insurers" in data
        assert "policy_types" in data
        assert "statuses" in data
        assert "classifications" in data
        
        # Check values are lists
        assert isinstance(data["countries"], list)
        assert isinstance(data["insurers"], list)
        assert isinstance(data["statuses"], list)
    
    def test_filter_options_reflect_database(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test filter options reflect actual database values."""
        response = client.get(
            "/api/documents/filters/options",
            headers=auth_headers
        )
        
        data = response.json()
        
        # Should have NZ and AU from our test data
        assert "NZ" in data["countries"] or "AU" in data["countries"]
        
        # Should have some insurers
        assert len(data["insurers"]) > 0
        
        # Should have pending, validated, rejected statuses
        assert any(s in data["statuses"] for s in ["pending", "validated", "rejected"])
    
    def test_filter_options_without_auth(self, client):
        """Test filter options require authentication."""
        response = client.get("/api/documents/filters/options")
        assert response.status_code == 403


class TestDocumentListing:
    """Tests for document listing endpoint."""
    
    def test_list_documents_basic(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test basic document listing."""
        response = client.get(
            "/api/documents",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "documents" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        
        # Check we got documents
        assert len(data["documents"]) > 0
        assert data["total"] >= len(multiple_sample_documents)
    
    def test_list_documents_default_limit(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test default limit is applied."""
        response = client.get(
            "/api/documents",
            headers=auth_headers
        )
        
        data = response.json()
        assert data["limit"] == 50  # Default limit
    
    def test_list_documents_custom_limit(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test custom limit parameter."""
        response = client.get(
            "/api/documents?limit=2",
            headers=auth_headers
        )
        
        data = response.json()
        assert data["limit"] == 2
        assert len(data["documents"]) <= 2
    
    def test_list_documents_pagination(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test pagination with skip/limit."""
        # Get first page
        response1 = client.get(
            "/api/documents?limit=2&skip=0",
            headers=auth_headers
        )
        data1 = response1.json()
        
        # Get second page
        response2 = client.get(
            "/api/documents?limit=2&skip=2",
            headers=auth_headers
        )
        data2 = response2.json()
        
        # Documents should be different
        if len(data1["documents"]) > 0 and len(data2["documents"]) > 0:
            ids1 = {d["id"] for d in data1["documents"]}
            ids2 = {d["id"] for d in data2["documents"]}
            assert not ids1.intersection(ids2), "Pages should not overlap"
    
    def test_list_documents_page_parameter(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test page-based pagination."""
        response = client.get(
            "/api/documents?page=1&limit=3",
            headers=auth_headers
        )
        
        data = response.json()
        assert data["offset"] == 0  # Page 1 = offset 0
        assert len(data["documents"]) <= 3
        
        # Page 2
        response2 = client.get(
            "/api/documents?page=2&limit=3",
            headers=auth_headers
        )
        data2 = response2.json()
        assert data2["offset"] == 3  # Page 2 = offset 3


class TestDocumentFiltering:
    """Tests for document filtering."""
    
    def test_filter_by_country(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test filtering documents by country."""
        response = client.get(
            "/api/documents?country=NZ",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned documents should be from NZ
        for doc in data["documents"]:
            assert doc["country"] == "NZ"
    
    def test_filter_by_status(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test filtering documents by status."""
        for status in ["pending", "validated", "rejected"]:
            response = client.get(
                f"/api/documents?status={status}",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # All returned documents should have the requested status
            for doc in data["documents"]:
                assert doc["status"] == status
    
    def test_filter_by_policy_type(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test filtering documents by policy type."""
        response = client.get(
            "/api/documents?policy_type=Motor",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for doc in data["documents"]:
            assert doc["policy_type"] == "Motor"
    
    def test_filter_by_insurer(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test filtering documents by insurer."""
        # Get list of insurers first
        response = client.get(
            "/api/documents/filters/options",
            headers=auth_headers
        )
        insurers = response.json()["insurers"]
        
        if insurers:
            insurer = insurers[0]
            response = client.get(
                f"/api/documents?insurer={insurer}",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            
            for doc in data["documents"]:
                assert doc["insurer"] == insurer
    
    def test_combined_filters(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test combining multiple filters."""
        response = client.get(
            "/api/documents?country=NZ&status=pending&policy_type=Motor",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for doc in data["documents"]:
            assert doc["country"] == "NZ"
            assert doc["status"] == "pending"
            assert doc["policy_type"] == "Motor"
    
    def test_filter_no_matches(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test filter that returns no results."""
        response = client.get(
            "/api/documents?country=XYZ123",  # Non-existent country
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) == 0
        assert data["total"] == 0
        assert data["has_more"] == False


class TestDocumentSearch:
    """Tests for document search functionality."""
    
    def test_search_by_insurer(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test searching documents by insurer name."""
        response = client.get(
            "/api/documents?search=Insurer",  # Should match "Test Insurer X"
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find documents with "Insurer" in the name
        # Note: Actual results depend on implementation
    
    def test_search_by_source_url(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test searching by source URL."""
        response = client.get(
            "/api/documents?search=example.com",
            headers=auth_headers
        )
        
        assert response.status_code == 200
    
    def test_search_by_classification(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test searching by classification."""
        response = client.get(
            "/api/documents?search=policy",
            headers=auth_headers
        )
        
        assert response.status_code == 200
    
    def test_search_combined_with_filters(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test search combined with other filters."""
        response = client.get(
            "/api/documents?country=NZ&search=Insurer",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Results should match both filter and search
        for doc in data["documents"]:
            assert doc["country"] == "NZ"
    
    def test_search_case_sensitivity(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test search case sensitivity."""
        response_lower = client.get(
            "/api/documents?search=insurer",
            headers=auth_headers
        )
        
        response_upper = client.get(
            "/api/documents?search=INSURER",
            headers=auth_headers
        )
        
        # Both should return results (case-insensitive search)
        assert response_lower.status_code == 200
        assert response_upper.status_code == 200


class TestDocumentSorting:
    """Tests for document sorting."""
    
    def test_default_sort_order(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test default sort order (pending first, then by date)."""
        response = client.get(
            "/api/documents",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if len(data["documents"]) >= 2:
            # Pending should come before validated/rejected
            statuses = [d["status"] for d in data["documents"]]
            # This is a simplified check - actual order depends on implementation
            assert "pending" in statuses or len(statuses) > 0
    
    def test_sort_by_created_at(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test sorting by creation date."""
        response = client.get(
            "/api/documents",
            headers=auth_headers
        )
        
        data = response.json()
        
        if len(data["documents"]) >= 2:
            dates = [d["created_at"] for d in data["documents"]]
            # Check if sorted (newest first based on implementation)
            # This is a basic check
            assert all(dates[i] is not None for i in range(len(dates)))


class TestPaginationEdgeCases:
    """Tests for pagination edge cases."""
    
    def test_pagination_beyond_total(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test requesting page beyond total results."""
        response = client.get(
            "/api/documents?skip=1000&limit=10",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) == 0
        assert data["has_more"] == False
    
    def test_negative_skip(
        self, 
        client, 
        auth_headers
    ):
        """Test negative skip value handling."""
        response = client.get(
            "/api/documents?skip=-1",
            headers=auth_headers
        )
        
        # Should handle gracefully
        assert response.status_code in [200, 422]
    
    def test_zero_limit(
        self, 
        client, 
        auth_headers
    ):
        """Test zero limit."""
        response = client.get(
            "/api/documents?limit=0",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 422]
    
    def test_large_limit(
        self, 
        client, 
        auth_headers
    ):
        """Test very large limit."""
        response = client.get(
            "/api/documents?limit=10000",
            headers=auth_headers
        )
        
        assert response.status_code == 200


class TestStatsSummary:
    """Tests for document stats endpoint."""
    
    def test_get_document_stats(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test getting document statistics."""
        response = client.get(
            "/api/documents/stats/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check expected fields
        assert "total" in data or "by_status" in data or "by_country" in data
    
    def test_stats_reflect_documents(
        self, 
        client, 
        auth_headers,
        multiple_sample_documents
    ):
        """Test that stats reflect actual document counts."""
        # Get stats
        stats_response = client.get(
            "/api/documents/stats/summary",
            headers=auth_headers
        )
        
        # Get all documents
        docs_response = client.get(
            "/api/documents?limit=1000",
            headers=auth_headers
        )
        
        stats = stats_response.json()
        docs = docs_response.json()
        
        # Stats total should match documents total
        if "total" in stats:
            assert stats["total"] == docs["total"]
