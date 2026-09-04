"""
Alembic env.py — Configuração do ambiente de migrations do projeto Monettra.

- A URL do banco é lida das variáveis de ambiente (.env.development)
- O target_metadata aponta para todos os schemas registrados no Base
- Suporta autogenerate: detecta automaticamente mudanças nos schemas SQLAlchemy
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# ---------------------------------------------------------------------------
# Importar todos os schemas para que o autogenerate os detecte
# Adicione novos schemas aqui conforme forem criados
# ---------------------------------------------------------------------------
from src.schemas.base import Base  # noqa: F401
from src.schemas.categories import CategorySchema  # noqa: F401
from src.schemas.subscription_renewals import SubscriptionRenewalSchema  # noqa: F401
from src.schemas.subscriptions import SubscriptionSchema  # noqa: F401
from src.schemas.transactions import TransactionSchema  # noqa: F401
from src.schemas.users import UserSchema  # noqa: F401

# ---------------------------------------------------------------------------
# Ler variáveis de ambiente do .env.development
# ---------------------------------------------------------------------------
from src.shared.utils.environment import environment

DATABASE_URL = (
    "postgresql+psycopg://"
    f"{environment.get('DATABASE_USER')}:"
    f"{environment.get('DATABASE_PASSWORD')}@"
    f"{environment.get('DATABASE_HOST')}:"
    f"{environment.get('DATABASE_PORT')}/"
    f"{environment.get('DATABASE_DB')}"
)

# ---------------------------------------------------------------------------
# Configuração Alembic
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Base.metadata contém todos os schemas registrados via herança de Base
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Modo offline: gera SQL sem se conectar ao banco."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online: conecta ao banco e aplica as migrations."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
