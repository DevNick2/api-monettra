"""
SEED — Categorias padrão do Monettra.

Executa a inserção das categorias default do sistema para um usuário específico.
Se a categoria já existir (mesmo título + user_id), o registro é ignorado (idempotente).

Uso via Docker:
    docker exec -it api python -m db.seed_categories --user-id 1

Ou como função importável pelos testes/scripts:
    from db.seed_categories import seed_categories
    seed_categories(user_id=1, session=session)
"""

import argparse
from sqlalchemy.orm import Session

from src.shared.services.postgres_services import PostgresServices
from src.shared.utils.environment import environment
from src.schemas.categories import CategorySchema

DEFAULT_CATEGORIES = [
    {"title": "Moradia",      "color": "#8b6914", "icon_name": "Home"},
    {"title": "Transporte",   "color": "#5a6e8b", "icon_name": "Car"},
    {"title": "Lazer",        "color": "#7a5a8b", "icon_name": "Gamepad2"},
    {"title": "Educação",     "color": "#5a8b6e", "icon_name": "GraduationCap"},
    {"title": "Investimentos","color": "#8b7a5a", "icon_name": "Briefcase"},
    {"title": "Saúde",        "color": "#a63d2f", "icon_name": "Heart"},
    {"title": "Salário",      "color": "#4a7a4a", "icon_name": "Zap"},
    {"title": "Outros",       "color": "#6e6e6e", "icon_name": "ShoppingCart"},
]


def seed_categories(user_id: int, session: Session) -> int:
    """
    Insere as categorias padrão para o user_id fornecido.
    Categorias já existentes (mesmo título + user_id) são ignoradas.

    Returns:
        Número de categorias efetivamente inseridas.
    """
    inserted = 0

    for cat in DEFAULT_CATEGORIES:
        existing = session.execute(
            __import__("sqlalchemy").select(CategorySchema)
            .where(CategorySchema.title == cat["title"])
            .where(CategorySchema.user_id == user_id)
            .where(CategorySchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()

        if existing:
            continue

        session.add(CategorySchema(
            title=cat["title"],
            color=cat["color"],
            icon_name=cat["icon_name"],
            user_id=user_id,
        ))
        inserted += 1

    session.commit()
    return inserted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed de categorias padrão do Monettra")
    parser.add_argument("--user-id", type=int, required=True, help="ID do usuário alvo")
    args = parser.parse_args()

    postgres = PostgresServices(
        dbname=environment.get("DATABASE_DB", "monettra"),
        port=int(environment.get("DATABASE_PORT", "5432")),
        host=environment.get("DATABASE_HOST", "localhost"),
        user=environment.get("DATABASE_USER", "postgres"),
        password=environment.get("DATABASE_PASSWORD", "postgres"),
    )
    engine = postgres.connection()
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        count = seed_categories(user_id=args.user_id, session=session)
        print(f"✅ Seed finalizado: {count} categorias inseridas para user_id={args.user_id}")
    finally:
        session.close()
