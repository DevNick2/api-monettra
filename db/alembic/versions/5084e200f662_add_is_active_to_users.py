"""add_is_active_to_users

Revision ID: 5084e200f662
Revises: 80ad28d3519d
Create Date: 2026-04-07

Adiciona coluna `is_active` à tabela `users` com default TRUE.
Usuários existentes recebem is_active = TRUE automaticamente.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "5084e200f662"
down_revision = "80ad28d3519d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
