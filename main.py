from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

from src.shared.utils.environment import env, environment
from src.shared.utils.errors import http_exception_handler, validation_exception_handler
from src.shared.services.di_services import ContainerService
from src.http.routes import router
import src.schemas  # Garante que todos os schemas sejam registrados no Base

container = ContainerService()
container.config.db.from_dict({
    "dbname": environment.get('DATABASE_DB'),
    "port": environment.get('DATABASE_PORT'),
    "host": environment.get('DATABASE_HOST'),
    "user": environment.get('DATABASE_USER'),
    "password": environment.get('DATABASE_PASSWORD')
})

db_service = container.db_service()
db_service.connection()


@asynccontextmanager
async def lifespan(app: FastAPI):
    container.wire(modules=[
        "src.http.routes",
        "src.modules.health.health_controller",
        "src.modules.users.users_controller",
        "src.modules.auth.auth_controller",
        "src.modules.transactions.transactions_controller",
        "src.modules.categories.categories_controller",
        "src.modules.analytics.analytics_controller",
        "src.modules.planning.planning_controller",
    ])
    app.include_router(router)
    yield


app: FastAPI = FastAPI(
    title="Monettra API",
    description="API do projeto Monettra — gestão financeira pessoal com assistente de IA.",
    version="0.1.0",
    lifespan=lifespan
)

# ---------------------------------------------------------------------------
# CORS — Permite requisições cross-origin do frontend
# ---------------------------------------------------------------------------
# Em development: localhost:8080 (frontend Next.js)
# Em production: substituir pelo domínio real via variável de ambiente
_raw_origins = environment.get('CORS_ORIGINS', 'http://localhost:8080')
allowed_origins = [origin.strip() for origin in _raw_origins.split(',')]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Exception Handlers Globais
# ---------------------------------------------------------------------------
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3000,
        reload=(env == "development"),
        access_log=True,
        log_level='debug',
        reload_delay=0.5,
        reload_excludes=[
            ".gitignore", ".python-version", "*.md",
            ".dockerignore", ".venv/*", "__pycache__/*", ".git/*"
        ]
    )