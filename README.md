# Monettra API

API do Monettra, projeto pessoal de gestão financeira, construída em Python com FastAPI.

### Stack

- FastAPI + Uvicorn
- PostgreSQL + Alembic (migrations)
- Docker / Docker Compose
- Arquitetura em módulos de domínio (DDD)

### Módulos

- `accounts`, `transactions`, `credit_cards`, `categories`, `subscriptions`, `planning`, `analytics` — núcleo de gestão financeira
- `ia_engine` — camada de IA para insights e automações sobre os dados financeiros
- `auth`, `users` — autenticação e gestão de usuários

### Rodando localmente

Pré-requisitos: Docker, `uv` como gerenciador de pacotes.

Consulte o `Makefile` para os comandos disponíveis (setup, run, migrations), ou:

```bash
uv sync
docker compose up -d
```
