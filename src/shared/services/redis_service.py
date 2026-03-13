"""
RedisService — Conexão e acesso ao Redis/Valkey para cache.

Variáveis de ambiente esperadas: REDIS_HOST, REDIS_PORT
"""

import redis
from src.shared.utils.environment import environment
from src.shared.utils.logger import logger


class RedisService:
    def __init__(self):
        host = environment.get("REDIS_HOST", "localhost")
        port = int(environment.get("REDIS_PORT", "6379"))
        try:
            self._client = redis.Redis(
                host=host,
                port=port,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            self._client.ping()
            logger.info(f"Redis conectado em {host}:{port}")
        except Exception as e:
            logger.warning(f"Redis indisponível ({host}:{port}): {e} — cache desativado")
            self._client = None

    @property
    def client(self) -> redis.Redis | None:
        return self._client

    def get(self, key: str) -> str | None:
        if not self._client:
            return None
        try:
            return self._client.get(key)
        except Exception as e:
            logger.warning(f"Redis GET falhou para '{key}': {e}")
            return None

    def set(self, key: str, value: str, ttl: int = 60) -> None:
        if not self._client:
            return
        try:
            self._client.setex(key, ttl, value)
        except Exception as e:
            logger.warning(f"Redis SET falhou para '{key}': {e}")

    def delete(self, key: str) -> None:
        if not self._client:
            return
        try:
            self._client.delete(key)
        except Exception as e:
            logger.warning(f"Redis DELETE falhou para '{key}': {e}")

    def delete_pattern(self, pattern: str) -> None:
        """Remove todas as chaves que casam com o padrão (ex: 'transactions:uid:42:*')."""
        if not self._client:
            return
        try:
            keys = self._client.keys(pattern)
            if keys:
                self._client.delete(*keys)
        except Exception as e:
            logger.warning(f"Redis delete_pattern falhou para '{pattern}': {e}")
