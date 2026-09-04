"""ia_token_usage_and_feature_flags

Revision ID: 24b4f6ad0582
Revises: 5084e200f662
Create Date: 2026-04-07

Cria:
- Enum `ia_operation` ('chat', 'ofx', 'tool')
- Tabela `ia_token_usage` para auditoria de consumo de IA
- Tabela `feature_flags` com seeds das 4 flags iniciais
- Tabela `account_feature_flags` para overrides por conta
"""

import sqlalchemy as sa
from alembic import op

revision = "24b4f6ad0582"
down_revision = "5084e200f662"
branch_labels = None
depends_on = None

_IA_OPERATION_ENUM = "ia_operation"


def upgrade() -> None:
    # ── ia_token_usage ──────────────────────────────────────────
    # O Enum é criado automaticamente pelo op.create_table (create_type default=True)
    op.create_table(
        "ia_token_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.Integer,
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "operation",
            sa.Enum("chat", "ofx", "tool", name=_IA_OPERATION_ENUM),
            nullable=False,
        ),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("tokens_input", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_ia_token_usage_account_id", "ia_token_usage", ["account_id"])
    op.create_index("ix_ia_token_usage_created_at", "ia_token_usage", ["created_at"])

    # ── feature_flags ───────────────────────────────────────────
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("enabled_global", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Seeds das 4 flags iniciais
    op.execute(
        """
        INSERT INTO feature_flags (name, description, enabled_global) VALUES
        ('subscriptions', 'Módulo de assinaturas recorrentes', true),
        ('credit_cards', 'Módulo de cartão de crédito e faturas', true),
        ('ia_chat', 'Assistente de IA — chat com o Escriba Real', true),
        ('ofx_import', 'Importação de extratos OFX', true)
        """
    )

    # ── account_feature_flags ───────────────────────────────────
    op.create_table(
        "account_feature_flags",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.Integer,
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "flag_name",
            sa.String(100),
            sa.ForeignKey("feature_flags.name", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("account_id", "flag_name", name="uq_account_feature_flag"),
    )
    op.create_index(
        "ix_account_feature_flags_account_id", "account_feature_flags", ["account_id"]
    )


def downgrade() -> None:
    op.drop_table("account_feature_flags")
    op.drop_table("feature_flags")
    op.drop_table("ia_token_usage")
    op.execute(f"DROP TYPE IF EXISTS {_IA_OPERATION_ENUM}")
