# PolicyCheck v6 Backend Tests

This directory contains comprehensive tests for the PolicyCheck v6 backend API.

## Test Structure

```
tests/
├── __init__.py                    # Test package initialization
├── conftest.py                    # Pytest fixtures and configuration
├── test_authentication.py         # Authentication and authorization tests
├── test_crawl_management.py       # Crawl session management tests
├── test_document_actions.py       # Document action tests (approve, reject, etc.)
├── test_document_upload.py        # Document upload tests (single + multiple files)
├── test_download_and_export.py    # Download and export functionality tests
└── test_filters_and_search.py     # Filtering and search tests
```

## Running Tests

### Run all tests
```bash
cd backend
pytest
```

### Run with coverage
```bash
cd backend
pytest --cov=app --cov-report=html --cov-report=term
```

### Run specific test file
```bash
cd backend
pytest tests/test_document_upload.py -v
```

### Run specific test class
```bash
cd backend
pytest tests/test_document_upload.py::TestMultipleFileUpload -v
```

### Run specific test method
```bash
cd backend
pytest tests/test_document_upload.py::TestMultipleFileUpload::test_upload_multiple_pdfs_simultaneously -v
```

### Run with markers
```bash
# Run only unit tests
cd backend
pytest -m unit

# Run only integration tests
cd backend
pytest -m integration

# Exclude slow tests
cd backend
pytest -m "not slow"
```

## Test Categories

### Document Upload Tests (`test_document_upload.py`)
- **Single File Upload**: Basic upload, authentication, validation
- **Multiple File Upload**: Batch uploads, mixed validity files
- **Upload Validation**: Empty files, special characters, size limits
- **Classification**: Upload triggers classification, error handling

### Document Actions Tests (`test_document_actions.py`)
- **Approve**: Approve pending/validated documents
- **Reject**: Reject documents
- **Archive**: Archive/reject documents
- **Reclassify**: Change document classification
- **Delete**: Delete documents with file cleanup
- **Download**: Single and bulk downloads
- **Preview**: PDF preview endpoint

### Crawl Management Tests (`test_crawl_management.py`)
- **Start Crawl**: Starting new crawl sessions, capacity limits
- **Status**: Getting crawl status, derived phases
- **Results**: Getting documents from crawl
- **List Sessions**: Pagination, user-specific lists
- **Delete**: Deleting crawls, cascade behavior
- **Logs**: Crawl log retrieval
- **Seed URLs**: URL discovery, custom insurers

### Authentication Tests (`test_authentication.py`)
- **Registration**: User registration, validation
- **Login**: Authentication, token generation
- **Token Validation**: Token expiration, invalid tokens
- **CSRF Protection**: CSRF token handling
- **Password Validation**: Strength requirements
- **Role-based Access**: Admin vs reviewer permissions

### Filters and Search Tests (`test_filters_and_search.py`)
- **Filter Options**: Getting distinct filter values
- **Document Listing**: Basic listing, pagination
- **Filtering**: By country, status, policy type, insurer
- **Search**: Text search functionality
- **Sorting**: Default and custom sort orders

### Download and Export Tests (`test_download_and_export.py`)
- **Single Download**: Individual file downloads
- **Bulk ZIP**: ZIP downloads with filters
- **CSV Export**: Export functionality
- **Validation**: Security checks, path traversal protection

## Key Features Tested

### Multiple File Upload
The test suite includes comprehensive tests for uploading multiple files:

```python
# Test batch upload behavior
def test_upload_multiple_pdfs_simultaneously(...)

# Test sequential multiple uploads
def test_sequential_multiple_uploads(...)

# Test mixed valid/invalid files
def test_upload_multiple_with_mixed_validity(...)
```

### CSRF Protection
All state-changing operations (POST, PUT, DELETE) require CSRF tokens:

```python
# Headers must include X-CSRF-Token for mutations
headers = {
    "Authorization": f"Bearer {token}",
    "X-CSRF-Token": csrf_token
}
```

### Database Isolation
Each test runs in a transaction that is rolled back after the test:
- Tests don't interfere with each other
- Database is clean for each test
- Fast execution with SQLite

## Fixtures

### Available Fixtures

- `client`: TestClient instance with overridden DB
- `db_session`: Database session in a transaction
- `test_user`: Standard test user
- `admin_user`: Admin user
- `auth_headers`: Headers with valid JWT token
- `auth_headers_with_csrf`: Headers with JWT and CSRF token
- `sample_document`: Single document for testing
- `multiple_sample_documents`: List of 5 test documents
- `sample_crawl_session`: Completed crawl session
- `sample_pdf_file`: Valid PDF file for upload

### Using Fixtures

```python
def test_example(client, auth_headers_with_csrf, sample_document):
    response = client.put(
        f"/api/documents/{sample_document.id}/approve",
        headers=auth_headers_with_csrf
    )
    assert response.status_code == 200
```

## Configuration

Test configuration is in `pytest.ini`:
- Verbose output
- Short traceback format
- Custom markers for test categorization
- Warning filters

## Adding New Tests

1. Create test function with `test_` prefix
2. Use appropriate fixtures
3. Group related tests in a class
4. Add markers for categorization
5. Document what the test verifies

Example:
```python
import pytest

class TestMyFeature:
    """Tests for my new feature."""
    
    @pytest.mark.unit
    def test_feature_does_x(self, client, auth_headers):
        """Test that feature correctly does X."""
        response = client.get("/api/feature", headers=auth_headers)
        assert response.status_code == 200
```

## CI/CD Integration

Tests can be run in CI/CD pipelines:

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-cov

# Run tests
cd backend
pytest --cov=app --cov-report=xml --cov-fail-under=80
```

## Troubleshooting

### Database locked errors
If you see SQLite database locked errors, ensure tests aren't running in parallel:
```bash
pytest -n 1  # Disable parallel execution
```

### CSRF token errors
Remember to use `auth_headers_with_csrf` for POST/PUT/DELETE operations.

### File not found errors
Upload tests use mocked classification service to avoid external dependencies.
