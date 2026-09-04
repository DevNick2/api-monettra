from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Any


class ErrorResponse(BaseModel):
    error: bool = True
    status: int
    message: str
    details: list[Any] | None = None


async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            status=exc.status_code,
            message=exc.detail or "Erro interno do servidor"
        ).model_dump()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(loc) for loc in err["loc"][1:]), "issue": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            status=422,
            message="Dados de entrada inválidos",
            details=details
        ).model_dump()
    )
