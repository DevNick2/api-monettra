"""add_payment_method_to_subscriptions

Revision ID: 3f8c1a2e9b0d
Revises: d2f7e41b92aa
Create Date: 2026-03-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3f8c1a2e9b0d"
down_revision: Union[str, Sequence[str], None] = "d2f7e41b92aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    subscription_payment_method = postgresql.ENUM(
        "default", "credit_card", name="subscription_payment_method"
    )
    subscription_payment_method.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "subscriptions",
        sa.Column(
            "payment_method",
            subscription_payment_method,
            nullable=False,
            server_default="default",
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "payment_method")

    subscription_payment_method = postgresql.ENUM(
        "default", "credit_card", name="subscription_payment_method"
    )
    subscription_payment_method.drop(op.get_bind(), checkfirst=True)
