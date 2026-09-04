"""add_account_invites

Revision ID: 3e7d9c1f4a82
Revises: 25c5f7b0e493
Create Date: 2026-04-11

Cria:
- Enum `invite_status` ('pending', 'sent', 'viewed', 'created')
- Tabela `account_invites` com token_hash, status, expires_at, revoked_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "3e7d9c1f4a82"
down_revision = "25c5f7b0e493"
branch_labels = None
depends_on = None

_INVITE_STATUS_ENUM = "invite_status"


def upgrade() -> None:
    op.create_table(
        "account_invites",
        sa.Column("id", sa.Integer, autoincrement=True, nullable=False),
        sa.Column(
            "code",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "account_id",
            sa.Integer,
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "viewed", "created", name=_INVITE_STATUS_ENUM),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("id", name="uq_account_invites_id"),
        sa.PrimaryKeyConstraint("id", "code"),
    )
    op.create_index("ix_account_invites_account_id", "account_invites", ["account_id"])
    op.create_index("ix_account_invites_email", "account_invites", ["email"])


def downgrade() -> None:
    op.drop_table("account_invites")
    op.execute(f"DROP TYPE IF EXISTS {_INVITE_STATUS_ENUM}")
