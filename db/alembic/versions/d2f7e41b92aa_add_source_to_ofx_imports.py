"""add_source_to_ofx_imports

Revision ID: d2f7e41b92aa
Revises: 7a90b4f84537
Create Date: 2026-03-26 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2f7e41b92aa"
down_revision: Union[str, Sequence[str], None] = "7a90b4f84537"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ofx_imports",
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="settings",
        ),
    )


def downgrade() -> None:
    op.drop_column("ofx_imports", "source")
