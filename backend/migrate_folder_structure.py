"""
Migration script: Reorganize existing files from insurer folders to policy_type folders.

Run this once after deploying the updated code to reorganize existing downloaded files.

Usage:
    cd backend
    python migrate_folder_structure.py
"""
import os
import shutil
from pathlib import Path

# Allow running as standalone script
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import get_db
from app.models import Document
from app.config import RAW_STORAGE_DIR


def migrate_to_policy_type_structure():
    """Migrate existing files from insurer folders to policy_type folders."""
    db = next(get_db())
    
    try:
        documents = db.query(Document).all()
        migrated = 0
        skipped = 0
        errors = 0
        
        print(f"Found {len(documents)} documents to process")
        print(f"Storage directory: {RAW_STORAGE_DIR}")
        
        for doc in documents:
            try:
                old_path = Path(doc.local_file_path)
                if not old_path.exists():
                    print(f"  [SKIP] File not found: {old_path}")
                    skipped += 1
                    continue
                
                # Determine new path based on policy_type
                policy_type = doc.policy_type or "General"
                new_dir = RAW_STORAGE_DIR / policy_type
                new_dir.mkdir(parents=True, exist_ok=True)
                new_path = new_dir / old_path.name
                
                # Handle filename collision
                if new_path.exists() and new_path != old_path:
                    base = old_path.stem
                    ext = old_path.suffix
                    counter = 1
                    while new_path.exists():
                        new_path = new_dir / f"{base}_{counter}{ext}"
                        counter += 1
                
                # Move file if path changed
                if old_path != new_path:
                    shutil.move(str(old_path), str(new_path))
                    
                    # Update database record
                    doc.local_file_path = str(new_path)
                    migrated += 1
                    
                    if migrated % 50 == 0:
                        print(f"  Migrated {migrated} files...")
                        db.commit()
                else:
                    skipped += 1
            
            except Exception as e:
                print(f"  [ERROR] Doc {doc.id}: {e}")
                errors += 1
        
        db.commit()
        print(f"\nMigration complete:")
        print(f"  Migrated: {migrated}")
        print(f"  Skipped:  {skipped}")
        print(f"  Errors:   {errors}")
        
        # Clean up empty directories
        cleanup_count = 0
        if RAW_STORAGE_DIR.exists():
            for item in RAW_STORAGE_DIR.iterdir():
                if item.is_dir() and not any(item.iterdir()):
                    item.rmdir()
                    cleanup_count += 1
        
        if cleanup_count:
            print(f"  Cleaned up {cleanup_count} empty directories")
    
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("PolicyCheck - Folder Structure Migration")
    print("Reorganizing files: insurer/ -> policy_type/")
    print("=" * 60)
    migrate_to_policy_type_structure()
