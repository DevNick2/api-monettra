"""create ofx_imports table (OFX import tracking)

Revision ID: d2f7e41b92aa
Revises: 7a90b4f84537
Create Date: 2026-03-26 11:10:00.000000

Nota: revisão original só fazia ADD COLUMN em ofx_imports, mas a tabela
nunca foi criada em migrações anteriores. Esta revisão cria a tabela completa
alinhada a OfxImportSchema (inclui source desde o início).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2f7e41b92aa"
down_revision: Union[str, Sequence[str], None] = "7a90b4f84537"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "ofx_imports" in inspector.get_table_names():
        # Tabela já existe (bases legadas): garantir coluna source
        cols = {c["name"] for c in inspector.get_columns("ofx_imports")}
        if "source" not in cols:
            op.add_column(
                "ofx_imports",
                sa.Column(
                    "source",
                    sa.String(length=50),
                    nullable=False,
                    server_default="settings",
                ),
            )
        return

    op.create_table(
        "ofx_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "code",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="settings",
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("total_transactions", sa.Integer(), nullable=True),
        sa.Column("processed_transactions", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_ofx_imports_code", "ofx_imports", ["code"])
    op.create_index("ix_ofx_imports_account_id", "ofx_imports", ["account_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "ofx_imports" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("ofx_imports")}
    # Tabela completa criada por esta revisão
    if "filename" in cols:
        op.drop_index("ix_ofx_imports_account_id", table_name="ofx_imports")
        op.drop_index("ix_ofx_imports_code", table_name="ofx_imports")
        op.drop_table("ofx_imports")
    elif "source" in cols:
        op.drop_column("ofx_imports", "source")
