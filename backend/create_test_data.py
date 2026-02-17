#!/usr/bin/env python3
"""
Test Data Generator for PolicyCheck

This script creates sample data for testing the application without running real crawls.
Run this inside the backend container.
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import CrawlSession, Document, User
from app.auth import get_password_hash


def create_test_data():
    """Create test crawl sessions and documents"""
    db = SessionLocal()
    
    try:
        # Ensure admin user exists
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                name="Admin User",
                hashed_password=get_password_hash("admin123"),
                is_admin=True
            )
            db.add(admin)
            db.commit()
            print("✓ Created admin user")
        
        # Create a completed crawl session
        crawl = CrawlSession(
            user_id=admin.id,
            country="NZ",
            status="completed",
            progress_pct=100,
            pages_scanned=45,
            pdfs_found=12,
            pdfs_downloaded=10,
            pdfs_filtered=2,
            errors_count=0,
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            completed_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=45),
        )
        db.add(crawl)
        db.commit()
        db.refresh(crawl)
        print(f"✓ Created test crawl session #{crawl.id}")
        
        # Create sample documents
        insurers = ["AA Insurance", "AMI Insurance", "Tower Insurance", "State Insurance"]
        policy_types = ["Home", "Motor", "Life", "Contents"]
        classifications = ["PDS", "Policy Wording", "Fact Sheet", "TMD", "General"]
        
        docs_created = 0
        for i, insurer in enumerate(insurers):
            for j, policy_type in enumerate(policy_types):
                # Skip some combinations
                if (i + j) % 3 == 0:
                    continue
                    
                doc = Document(
                    crawl_session_id=crawl.id,
                    source_url=f"https://www.{insurer.lower().replace(' ', '')}.co.nz/products/{policy_type.lower()}/document.pdf",
                    insurer=insurer,
                    local_file_path=f"/app/storage/{insurer}/{policy_type}_Policy.pdf",
                    file_size=(i + 1) * (j + 1) * 150000,  # Simulated file size
                    file_hash=f"mock_hash_{i}_{j}_{insurer}_{policy_type}",
                    country="NZ",
                    policy_type=policy_type,
                    document_type=classifications[i % len(classifications)],
                    classification=classifications[i % len(classifications)],
                    confidence=0.75 + (i * 0.05),
                    status="pending" if i % 3 == 0 else "validated",
                    created_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=30 - (i*10)),
                )
                db.add(doc)
                docs_created += 1
        
        db.commit()
        print(f"✓ Created {docs_created} test documents")
        
        # Summary
        print("\n" + "="*50)
        print("Test Data Created Successfully!")
        print("="*50)
        print(f"\nCrawl Sessions: 1")
        print(f"Documents: {docs_created}")
        print(f"\nLogin to the application with:")
        print(f"  Username: admin")
        print(f"  Password: admin123")
        print(f"\nNote: Documents reference mock files that don't exist.")
        print(f"Downloads will fail, but you can see the UI and filtering.")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"✗ Error creating test data: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_test_data()
