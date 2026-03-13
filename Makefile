# ============================================================
# Monettra API — Makefile
# ============================================================

# Gera uma nova migration automaticamente comparando os schemas
# com o estado atual do banco (autogenerate).
# Uso: make migration name="descricao_da_mudanca"
migration:
	docker exec -it api uv run alembic revision --autogenerate -m "$(name)"

# Aplica todas as migrations pendentes (upgrade para a última versão)
run-migrations:
	docker exec -it api uv run alembic upgrade head

# Reverte a última migration aplicada
rollback:
	docker exec -it api uv run alembic downgrade -1

# Exibe o histórico de migrations e qual está aplicada atualmente
migration-status:
	docker exec -it api uv run alembic current
	docker exec -it api uv run alembic history --verbose

# Corrige permissões dos arquivos de migration criados pelo Docker (ficam como root)
fix-permissions:
	docker exec -u root api chown -R $(shell id -u):$(shell id -g) /app/db/alembic/versions/

# Executa o seed de categorias padrão para um usuário específico
# Uso: make seed-categories user_id=1
seed-categories:
	docker exec -it api uv run python -m db.seed_categories --user-id $(user_id)

# ============================================================
# Docker
# ============================================================

# Refaz os containers e força o build das imagens
build:
	docker compose up --no-deps --build -d

# Remove os containers
stop:
	docker compose down

# Sobe os containers
run:
	docker compose up -d

# Ativa o monitoramento do container em desenvolvimento
watch:
	docker compose logs -f api