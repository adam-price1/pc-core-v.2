"""Initial schema

Revision ID: 20260213_0001
Revises:
Create Date: 2026-02-13 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260213_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("country", sa.String(length=5), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "crawl_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("country", sa.String(length=10), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("max_minutes", sa.Integer(), nullable=False),
        sa.Column("seed_urls", sa.JSON(), nullable=False),
        sa.Column("policy_types", sa.JSON(), nullable=False),
        sa.Column("keyword_filters", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=True),
        sa.Column("pages_scanned", sa.Integer(), nullable=True),
        sa.Column("pdfs_found", sa.Integer(), nullable=True),
        sa.Column("pdfs_downloaded", sa.Integer(), nullable=True),
        sa.Column("pdfs_filtered", sa.Integer(), nullable=True),
        sa.Column("errors_count", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crawl_sessions_status", "crawl_sessions", ["status"], unique=False)
    op.create_index("ix_crawl_sessions_country", "crawl_sessions", ["country"], unique=False)
    op.create_index("ix_crawl_sessions_created_at", "crawl_sessions", ["created_at"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("insurer", sa.String(length=255), nullable=False),
        sa.Column("local_file_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=10), nullable=False),
        sa.Column("policy_type", sa.String(length=100), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("classification", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("crawl_session_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["crawl_session_id"],
            ["crawl_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_crawl_session", "documents", ["crawl_session_id"], unique=False)
    op.create_index(
        "ix_documents_country_policy_type",
        "documents",
        ["country", "policy_type"],
        unique=False,
    )
    op.create_index("ix_documents_crawl_status", "documents", ["crawl_session_id", "status"], unique=False)
    op.create_index("ix_documents_country", "documents", ["country"], unique=False)
    op.create_index("ix_documents_policy_type", "documents", ["policy_type"], unique=False)
    op.create_index("ix_documents_classification", "documents", ["classification"], unique=False)
    op.create_index("ix_documents_created_at", "documents", ["created_at"], unique=False)
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_name", sa.String(length=200), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], unique=False)
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"], unique=False)
    op.create_index("ix_audit_log_action", "audit_log", ["action"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_file_hash", table_name="documents")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_classification", table_name="documents")
    op.drop_index("ix_documents_policy_type", table_name="documents")
    op.drop_index("ix_documents_country", table_name="documents")
    op.drop_index("ix_documents_crawl_status", table_name="documents")
    op.drop_index("ix_documents_country_policy_type", table_name="documents")
    op.drop_index("ix_documents_crawl_session", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_crawl_sessions_created_at", table_name="crawl_sessions")
    op.drop_index("ix_crawl_sessions_country", table_name="crawl_sessions")
    op.drop_index("ix_crawl_sessions_status", table_name="crawl_sessions")
    op.drop_table("crawl_sessions")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
