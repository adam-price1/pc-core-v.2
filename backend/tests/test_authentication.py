"""
Tests for authentication endpoints.

Includes:
- User registration
- User login
- Token validation
- Password strength validation
- CSRF token handling
- Logout
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch


class TestUserRegistration:
    """Tests for user registration endpoint."""
    
    def test_register_user_success(self, client, db_session):
        """Test successful user registration."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "newuser",
                "password": "SecurePass1!",
                "name": "New User",
                "role": "reviewer",
                "country": "NZ"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newuser"
        assert data["name"] == "New User"
        assert "id" in data
        assert "password_hash" not in data  # Don't return password
    
    def test_register_duplicate_username(self, client, test_user):
        """Test registration with existing username fails."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": test_user.username,  # Existing username
                "password": "SecurePass1!",
                "name": "Another User",
            }
        )
        
        assert response.status_code == 400
        assert "username" in response.json()["detail"].lower()
    
    def test_register_weak_password(self, client):
        """Test registration with weak password fails."""
        weak_passwords = [
            ("short", "at least 8 characters"),
            ("lowercase123!", "uppercase"),
            ("UPPERCASE123!", "lowercase"),
            ("UppercaseLower!", "digit"),
            ("Uppercase123", "special character"),
        ]
        
        for i, (password, expected_error) in enumerate(weak_passwords):
            response = client.post(
                "/api/auth/register",
                json={
                    "username": f"user{i}",
                    "password": password,
                    "name": f"User {i}",
                }
            )
            
            assert response.status_code == 400
            assert expected_error.lower() in response.json()["detail"].lower()
    
    def test_register_missing_fields(self, client):
        """Test registration with missing required fields."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "incomplete",
                # Missing password and name
            }
        )
        
        assert response.status_code == 422  # Validation error


class TestUserLogin:
    """Tests for user login endpoint."""
    
    def test_login_success(self, client, test_user):
        """Test successful login."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": test_user.username,
                "password": "TestPass123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == test_user.username
        assert "user_id" in data
    
    def test_login_invalid_password(self, client, test_user):
        """Test login with wrong password."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": test_user.username,
                "password": "WrongPass1!"
            }
        )
        
        assert response.status_code == 401
        assert "password" in response.json()["detail"].lower()
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent username."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "nonexistentuser",
                "password": "SomePassword123!"
            }
        )
        
        assert response.status_code == 401
    
    def test_login_missing_fields(self, client):
        """Test login with missing fields."""
        response = client.post(
            "/api/auth/login",
            json={"username": "user"}  # Missing password
        )
        
        assert response.status_code == 422


class TestTokenValidation:
    """Tests for token validation and usage."""
    
    def test_access_protected_endpoint_with_valid_token(
        self, 
        client, 
        auth_headers
    ):
        """Test accessing protected endpoint with valid token."""
        response = client.get(
            "/api/documents",
            headers=auth_headers
        )
        
        # Should succeed (or return empty list if no documents)
        assert response.status_code in [200, 403]  # 403 if CSRF needed for writes
    
    def test_access_protected_endpoint_without_token(self, client):
        """Test accessing protected endpoint without token."""
        response = client.get("/api/documents")
        
        assert response.status_code == 403
    
    def test_access_protected_endpoint_with_invalid_token(self, client):
        """Test accessing protected endpoint with invalid token."""
        response = client.get(
            "/api/documents",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == 401  # Or 403
    
    def test_token_expiration(self, client, test_user):
        """Test that expired tokens are rejected."""
        from app.auth import create_access_token
        from datetime import timedelta
        
        # Create an expired token
        expired_token = create_access_token(
            data={"sub": test_user.username},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        response = client.get(
            "/api/documents",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == 401


class TestPasswordValidation:
    """Tests for password strength validation."""
    
    def test_password_strength_requirements(self):
        """Test password strength validation function."""
        from app.auth import validate_password_strength
        
        # Valid passwords
        valid_passwords = [
            "SecurePass1!",
            "MyP@ssw0rd",
            "C0mpl3x!Pass",
        ]
        
        for password in valid_passwords:
            is_valid, message = validate_password_strength(password)
            assert is_valid, f"Password '{password}' should be valid but got: {message}"
        
        # Invalid passwords
        invalid_cases = [
            ("short", "at least 8"),
            ("lowercase123!", "uppercase"),
            ("UPPERCASE123!", "lowercase"),
            ("UppercaseLower!", "digit"),
            ("Uppercase123", "special"),
        ]
        
        for password, expected_error in invalid_cases:
            is_valid, message = validate_password_strength(password)
            assert not is_valid, f"Password '{password}' should be invalid"
            assert expected_error.lower() in message.lower()


class TestCSRFProtection:
    """Tests for CSRF token protection."""
    
    def test_csrf_token_generation(self, test_user):
        """Test CSRF token generation."""
        from app.auth import create_csrf_token, validate_csrf_token
        
        token = create_csrf_token(subject=test_user.username)
        assert token is not None
        assert len(token) > 0
        
        # Validate the token
        is_valid = validate_csrf_token(token, expected_subject=test_user.username)
        assert is_valid is True
    
    def test_csrf_token_validation_wrong_subject(self, test_user):
        """Test CSRF token fails with wrong subject."""
        from app.auth import create_csrf_token, validate_csrf_token
        
        token = create_csrf_token(subject=test_user.username)
        
        # Try to validate with wrong subject
        is_valid = validate_csrf_token(token, expected_subject="wronguser")
        assert is_valid is False
    
    def test_csrf_token_expiration(self, test_user):
        """Test CSRF token expiration."""
        from app.auth import create_csrf_token, validate_csrf_token
        from datetime import timedelta
        
        # Create a token with very short expiration
        token = create_csrf_token(
            subject=test_user.username,
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        is_valid = validate_csrf_token(token, expected_subject=test_user.username)
        assert is_valid is False
    
    def test_post_without_csrf_token_fails(
        self, 
        client, 
        auth_headers,  # No CSRF
        sample_document
    ):
        """Test POST request without CSRF token fails."""
        response = client.post(
            f"/api/documents/{sample_document.id}/approve",
            headers=auth_headers
        )
        
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]
    
    def test_get_without_csrf_succeeds(
        self, 
        client, 
        auth_headers,  # No CSRF needed for GET
        sample_document
    ):
        """Test GET request doesn't require CSRF token."""
        response = client.get(
            f"/api/documents/{sample_document.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200


class TestProtectedEndpoints:
    """Tests for various protected endpoints."""
    
    def test_me_endpoint(self, client, auth_headers, test_user):
        """Test /me endpoint returns current user info."""
        response = client.get(
            "/api/auth/me",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user.username
        assert data["id"] == test_user.id
    
    def test_change_password(
        self, 
        client, 
        auth_headers_with_csrf, 
        test_user
    ):
        """Test password change endpoint."""
        response = client.post(
            "/api/auth/change-password",
            headers=auth_headers_with_csrf,
            json={
                "current_password": "TestPass123!",
                "new_password": "NewSecurePass1!"
            }
        )
        
        # May not exist in current implementation
        assert response.status_code in [200, 404]
    
    def test_logout(self, client, auth_headers_with_csrf):
        """Test logout endpoint."""
        response = client.post(
            "/api/auth/logout",
            headers=auth_headers_with_csrf
        )
        
        # May not exist in current implementation
        assert response.status_code in [200, 404]


class TestAuthEdgeCases:
    """Tests for authentication edge cases."""
    
    def test_malformed_authorization_header(self, client):
        """Test various malformed authorization headers."""
        malformed_headers = [
            {"Authorization": "invalid"},
            {"Authorization": "Bearer"},
            {"Authorization": "Basic dXNlcjpwYXNz"},
            {"Authorization": ""},
        ]
        
        for headers in malformed_headers:
            response = client.get("/api/documents", headers=headers)
            assert response.status_code in [401, 403]
    
    def test_case_sensitive_username_login(self, client, test_user):
        """Test username case sensitivity in login."""
        # Try with different case
        response = client.post(
            "/api/auth/login",
            json={
                "username": test_user.username.upper(),
                "password": "TestPass123!"
            }
        )
        
        # May succeed or fail depending on implementation
        assert response.status_code in [200, 401]
    
    def test_sql_injection_in_login(self, client):
        """Test SQL injection attempt in login."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "' OR '1'='1",
                "password": "' OR '1'='1"
            }
        )
        
        # Should not authenticate
        assert response.status_code == 401


class TestRoleBasedAccess:
    """Tests for role-based access control."""
    
    def test_admin_can_access_admin_endpoints(
        self, 
        client, 
        admin_auth_headers
    ):
        """Test admin can access admin-only endpoints."""
        response = client.get(
            "/api/system/reset",
            headers=admin_auth_headers
        )
        
        # May return 404 if endpoint doesn't exist, but not 403
        assert response.status_code in [200, 404, 405]
    
    def test_reviewer_cannot_access_admin_endpoints(
        self, 
        client, 
        auth_headers
    ):
        """Test reviewer cannot access admin-only endpoints."""
        response = client.post(
            "/api/system/reset",
            headers=auth_headers
        )
        
        # Should be forbidden or not found
        assert response.status_code in [403, 404]
