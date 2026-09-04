"""add_base_schema_cols_ia_and_flags

Alinha `ia_token_usage`, `feature_flags` e `account_feature_flags` ao `BaseSchema`
(code UUID, updated_at, deleted_at, PK composta id+code).

Revision ID: 25c5f7b0e493
Revises: 24b4f6ad0582
Create Date: 2026-04-11

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "25c5f7b0e493"
down_revision = "24b4f6ad0582"
branch_labels = None
depends_on = None


def _upgrade_table(table: str) -> None:
    op.add_column(
        table,
        sa.Column(
            "code",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        table,
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(f"{table}_pkey", table, type_="primary")
    op.create_unique_constraint(f"uq_{table}_id", table, ["id"])
    op.create_primary_key(f"{table}_pkey", table, ["id", "code"])


def _downgrade_table(table: str) -> None:
    op.drop_constraint(f"{table}_pkey", table, type_="primary")
    op.drop_constraint(f"uq_{table}_id", table, type_="unique")
    op.create_primary_key(f"{table}_pkey", table, ["id"])
    op.drop_column(table, "deleted_at")
    op.drop_column(table, "updated_at")
    op.drop_column(table, "code")


def upgrade() -> None:
    for t in ("ia_token_usage", "feature_flags", "account_feature_flags"):
        _upgrade_table(t)


def downgrade() -> None:
    for t in ("account_feature_flags", "feature_flags", "ia_token_usage"):
        _downgrade_table(t)
