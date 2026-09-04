"""
rate_limit — helper simples de rate limiting via Redis.

Uso:
    rate_limit(request, key="invite_validate:TOKEN", max_requests=10, window_seconds=60)

Se Redis estiver indisponível, a checagem é pulada (fail-open).
"""

from fastapi import HTTPException, Request

from src.shared.utils.logger import logger

_redis_client = None


def _get_redis():
    """Lazy-load do cliente Redis para evitar import circular."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis as _redis
            from src.shared.utils.environment import environment

            host = environment.get("REDIS_HOST", "localhost")
            port = int(environment.get("REDIS_PORT", "6379"))
            _redis_client = _redis.Redis(
                host=host, port=port, decode_responses=True, socket_connect_timeout=1
            )
            _redis_client.ping()
        except Exception as exc:
            logger.warning(f"[rate_limit] Redis indisponível: {exc}")
            _redis_client = False  # type: ignore[assignment]
    return _redis_client if _redis_client else None


def rate_limit(
    request: Request,
    key: str,
    max_requests: int = 10,
    window_seconds: int = 60,
) -> None:
    """
    Verifica e incrementa o contador de requisições para `key`.
    Lança HTTPException(429) se o limite for excedido.
    Falha aberta se Redis estiver indisponível.
    """
    client = _get_redis()
    if client is None:
        return

    full_key = f"rl:{key}"
    try:
        count = client.incr(full_key)
        if count == 1:
            client.expire(full_key, window_seconds)
        if count > max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Muitas requisições. Tente novamente em {window_seconds} segundos.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[rate_limit] Erro ao verificar limite para '{full_key}': {exc}")
