"""Jerarquía de excepciones de Shiba.

Todas las excepciones públicas heredan de :class:`ShibaError`. Cada
instancia puede llevar un :class:`~shiba.error_codes.ErrorCode` estable
que permite al cliente identificar el error sin depender del mensaje.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shiba.error_codes import ErrorCode


class ShibaError(Exception):
    """Excepción base de la librería.

    :param message: descripción legible.
    :param code: :class:`ErrorCode` opcional. Si se omite, la excepción
        sigue siendo válida pero el cliente no podrá hacer match por
        código.
    :param details: información estructurada adicional (no PII).
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details: dict[str, Any] = details or {}

    def __str__(self) -> str:
        if self.code is None:
            return self.message
        return f"[{self.code.code}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict para responder por HTTP/JSON."""
        return {
            "code": self.code.code if self.code else None,
            "name": self.code.name if self.code else None,
            "message": self.message,
            "details": self.details,
        }


class ConnectionError(ShibaError):  # noqa: A001 - sombrea builtin a propósito
    """Falla al abrir o mantener la conexión con la base de datos."""


class QueryError(ShibaError):
    """Falla al ejecutar una sentencia SQL.

    Adjunta la query y los parámetros para facilitar el debug; nunca se
    deben loggear directamente si contienen PII.
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        query: str | None = None,
        params: Any = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)
        self.query = query
        self.params = params
        if cause is not None:
            self.__cause__ = cause


class IntegrityError(QueryError):
    """Violación de constraint (PK duplicada, FK, NOT NULL, CHECK)."""


class SchemaError(ShibaError):
    """Error en la definición de esquema (DDL inválida, identificador no permitido)."""


class MissingDataError(ShibaError):
    """Faltan datos requeridos para construir una operación."""


__all__ = [
    "ConnectionError",
    "IntegrityError",
    "MissingDataError",
    "QueryError",
    "SchemaError",
    "ShibaError",
]
