#!/usr/bin/env python3
"""
Migration Script: Update auto-classified documents from 'validated' to 'auto-approved'.

Run inside the backend container:
    docker exec -it project-policy-v1-main-backend-1 python migrate_auto_approved.py

This fixes existing records that were auto-classified with high confidence
but incorrectly marked as 'validated' (which shows as "Manually Approved").
"""
import sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import Document


def migrate():
    db = SessionLocal()
    try:
        # Find all "validated" documents that have classification metadata
        # indicating they were auto-classified (not manually approved)
        docs = db.query(Document).filter(
            Document.status == "validated"
        ).all()

        updated = 0
        for doc in docs:
            # Check if doc was auto-classified (has metadata from rule-based classifier)
            metadata = doc.metadata_json or {}
            is_auto = metadata.get("classification_method") == "rule-based-v2"
            
            # Also treat high-confidence docs without manual audit entries as auto-classified
            if is_auto or (doc.confidence and doc.confidence >= 0.85):
                doc.status = "auto-approved"
                updated += 1

        if updated > 0:
            db.commit()
            print(f"✓ Updated {updated} documents from 'validated' to 'auto-approved'")
        else:
            print("No documents needed updating.")

        # Also update any "pending" docs to "needs-review" for consistency
        pending_docs = db.query(Document).filter(Document.status == "pending").all()
        pending_updated = 0
        for doc in pending_docs:
            doc.status = "needs-review"
            pending_updated += 1

        if pending_updated > 0:
            db.commit()
            print(f"✓ Updated {pending_updated} documents from 'pending' to 'needs-review'")

        print("\nMigration complete!")

    except Exception as e:
        print(f"✗ Migration error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
