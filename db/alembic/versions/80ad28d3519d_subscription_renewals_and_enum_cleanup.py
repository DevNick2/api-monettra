"""subscription_renewals_and_enum_cleanup

Revision ID: 80ad28d3519d
Revises: bf0587e8b1c4
Create Date: 2026-04-07

Etapa 1 — Converte dados obsoletos (biannual/quarterly/semiannual → monthly).
Etapa 2 — Remove os 3 valores do enum nativo recurrence_type no PostgreSQL.
Etapa 3 — Cria tabela subscription_renewals com histórico de renovações.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "80ad28d3519d"
down_revision = "bf0587e8b1c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Etapa 1 — Converter dados obsoletos antes de alterar o enum
    # O banco armazena os nomes do enum em uppercase (BIANNUAL, MONTHLY, etc.)
    # -----------------------------------------------------------------------
    op.execute(
        "UPDATE subscriptions SET recurrence = 'MONTHLY'::recurrence_type "
        "WHERE recurrence::text IN ('BIANNUAL', 'QUARTERLY', 'SEMIANNUAL')"
    )

    # -----------------------------------------------------------------------
    # Etapa 2 — Recriar enum nativo com apenas MONTHLY e YEARLY
    # -----------------------------------------------------------------------
    op.execute("ALTER TYPE recurrence_type RENAME TO recurrence_type_old")
    op.execute("CREATE TYPE recurrence_type AS ENUM ('MONTHLY', 'YEARLY')")
    op.execute(
        "ALTER TABLE subscriptions "
        "ALTER COLUMN recurrence TYPE recurrence_type "
        "USING recurrence::text::recurrence_type"
    )
    op.execute("DROP TYPE recurrence_type_old")

    # -----------------------------------------------------------------------
    # Etapa 3 — Criar tabela subscription_renewals
    # -----------------------------------------------------------------------
    op.create_table(
        "subscription_renewals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "code",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("renewed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_billing_date", sa.Date(), nullable=False),
        sa.Column("new_billing_date", sa.Date(), nullable=False),
        sa.Column("days_overdue", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.ForeignKeyConstraint(["renewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id", "code"),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_subscription_renewals_subscription_id",
        "subscription_renewals",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscription_renewals_subscription_id",
        table_name="subscription_renewals",
    )
    op.drop_table("subscription_renewals")

    op.execute("ALTER TYPE recurrence_type RENAME TO recurrence_type_old")
    op.execute(
        "CREATE TYPE recurrence_type AS ENUM "
        "('MONTHLY', 'YEARLY', 'BIANNUAL', 'QUARTERLY', 'SEMIANNUAL')"
    )
    op.execute(
        "ALTER TABLE subscriptions "
        "ALTER COLUMN recurrence TYPE recurrence_type "
        "USING recurrence::text::recurrence_type"
    )
    op.execute("DROP TYPE recurrence_type_old")
