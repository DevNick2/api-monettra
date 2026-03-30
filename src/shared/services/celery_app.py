"""
Celery App — Configuração do worker de tarefas assíncronas do Monettra.

Broker  : Redis (compartilhado com o cache da aplicação)
Backend : Redis (armazena resultados das tasks)
"""

from celery import Celery
from src.shared.utils.environment import environment

REDIS_HOST = environment.get("REDIS_HOST", "redis")
REDIS_PORT = environment.get("REDIS_PORT", "6379")
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"

celery_app = Celery(
    "monettra",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.shared.services.ia_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
