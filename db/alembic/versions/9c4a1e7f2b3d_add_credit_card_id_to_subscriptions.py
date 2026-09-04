"""add_credit_card_id_to_subscriptions

Revision ID: 9c4a1e7f2b3d
Revises: 3e7d9c1f4a82
Create Date: 2026-07-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c4a1e7f2b3d"
down_revision: str | Sequence[str] | None = "3e7d9c1f4a82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions", sa.Column("credit_card_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_subscriptions_credit_card_id",
        "subscriptions",
        "credit_cards",
        ["credit_card_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_subscriptions_credit_card_id", "subscriptions", type_="foreignkey"
    )
    op.drop_column("subscriptions", "credit_card_id")
