"""credit_cards_and_invoices

Revision ID: c9f2a4b1d8e7
Revises: 3f8c1a2e9b0d
Create Date: 2026-03-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c9f2a4b1d8e7"
down_revision: Union[str, Sequence[str], None] = "3f8c1a2e9b0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Adicionar 'credit_card' ao enum transaction_classification
    op.execute(
        "ALTER TYPE transaction_classification ADD VALUE IF NOT EXISTS 'credit_card'"
    )

    # 2. Criar tabela credit_cards
    op.create_table(
        "credit_cards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "code",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("credit_limit", sa.Integer(), nullable=False),
        sa.Column("closing_day", sa.Integer(), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_credit_cards_code", "credit_cards", ["code"])
    op.create_index("ix_credit_cards_account_id", "credit_cards", ["account_id"])

    # 3. Criar tabela invoices
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "code",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("reference_month", sa.Integer(), nullable=False),
        sa.Column("reference_year", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "credit_card_id",
            sa.Integer(),
            sa.ForeignKey("credit_cards.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_invoices_code", "invoices", ["code"])
    op.create_index("ix_invoices_credit_card_id", "invoices", ["credit_card_id"])

    # 4. Adicionar invoice_id às transactions (nullable — não impacta dados existentes)
    op.add_column(
        "transactions",
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_transactions_invoice_id", "transactions", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_invoice_id", table_name="transactions")
    op.drop_column("transactions", "invoice_id")

    op.drop_index("ix_invoices_credit_card_id", table_name="invoices")
    op.drop_index("ix_invoices_code", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_credit_cards_account_id", table_name="credit_cards")
    op.drop_index("ix_credit_cards_code", table_name="credit_cards")
    op.drop_table("credit_cards")
