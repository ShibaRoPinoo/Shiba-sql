"""Catálogo de códigos de error propios de Shiba.

Cada error público lleva un :class:`ErrorCode` estable e independiente
del driver subyacente. Esto permite al cliente:

* identificar el error sin depender del mensaje (puede estar i18n),
* mapear errores nativos (pymysql, psycopg, etc.) a un dominio común,
* serializar el error sobre HTTP/JSON manteniendo semántica.

Convención de códigos
---------------------
* **SHIBA-1xxx** — Conexión / pool
* **SHIBA-2xxx** — Query / SQL
* **SHIBA-3xxx** — Esquema / DDL
* **SHIBA-4xxx** — Integridad
* **SHIBA-5xxx** — Transacciones / concurrencia
* **SHIBA-6xxx** — Datos / validación
* **SHIBA-9xxx** — Genéricos / no clasificados

Uso
---
.. code-block:: python

    from shiba import error_codes, ShibaError

    try:
        ...
    except ShibaError as e:
        if e.code is error_codes.INTEGRITY_DUPLICATE_KEY:
            ...
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from shiba.errors import (
    ConnectionError,
    IntegrityError,
    MissingDataError,
    QueryError,
    SchemaError,
    ShibaError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class ErrorCode:
    """Descriptor inmutable de un error de la librería."""

    code: str
    name: str
    default_message: str
    exception_class: type[ShibaError]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"

    def build(self, message: str | None = None, **kwargs: Any) -> ShibaError:
        """Construye (sin lanzar) la excepción asociada con este código."""
        msg = message or self.default_message
        return self.exception_class(msg, code=self, **kwargs)

    def raise_(self, message: str | None = None, **kwargs: Any) -> NoReturn:
        """Lanza la excepción asociada con este código.

        Para ``QueryError`` y descendientes acepta ``query=``, ``params=``,
        ``cause=``. Todas las clases aceptan ``details=``.
        """
        raise self.build(message, **kwargs)


# --- SHIBA-1xxx — Conexión / pool -------------------------------------------

CONNECTION_REFUSED = ErrorCode(
    "SHIBA-1001",
    "CONNECTION_REFUSED",
    "No se pudo establecer la conexión con el servidor.",
    ConnectionError,
)
CONNECTION_LOST = ErrorCode(
    "SHIBA-1002",
    "CONNECTION_LOST",
    "La conexión con el servidor se perdió.",
    ConnectionError,
)
AUTH_FAILED = ErrorCode(
    "SHIBA-1003",
    "AUTH_FAILED",
    "Autenticación rechazada por el servidor.",
    ConnectionError,
)
CONNECTION_TIMEOUT = ErrorCode(
    "SHIBA-1004",
    "CONNECTION_TIMEOUT",
    "La conexión excedió el tiempo de espera.",
    ConnectionError,
)
POOL_EXHAUSTED = ErrorCode(
    "SHIBA-1005",
    "POOL_EXHAUSTED",
    "El pool de conexiones está agotado.",
    ConnectionError,
)
CONNECTION_NOT_OPEN = ErrorCode(
    "SHIBA-1006",
    "CONNECTION_NOT_OPEN",
    "Se intentó operar sobre una conexión cerrada o no inicializada.",
    ConnectionError,
)

# --- SHIBA-2xxx — Query / SQL -----------------------------------------------

QUERY_SYNTAX_ERROR = ErrorCode(
    "SHIBA-2001",
    "QUERY_SYNTAX_ERROR",
    "Error de sintaxis SQL.",
    QueryError,
)
UNKNOWN_TABLE = ErrorCode(
    "SHIBA-2002",
    "UNKNOWN_TABLE",
    "La tabla referenciada no existe.",
    QueryError,
)
UNKNOWN_COLUMN = ErrorCode(
    "SHIBA-2003",
    "UNKNOWN_COLUMN",
    "La columna referenciada no existe.",
    QueryError,
)
EMPTY_QUERY = ErrorCode(
    "SHIBA-2004",
    "EMPTY_QUERY",
    "Se intentó ejecutar una query vacía.",
    QueryError,
)
INVALID_QUERY_PARAMS = ErrorCode(
    "SHIBA-2005",
    "INVALID_QUERY_PARAMS",
    "Los parámetros proporcionados no son válidos para la query.",
    QueryError,
)
QUERY_EXECUTION_FAILED = ErrorCode(
    "SHIBA-2099",
    "QUERY_EXECUTION_FAILED",
    "Falla genérica al ejecutar la query.",
    QueryError,
)

# --- SHIBA-3xxx — Schema / DDL ----------------------------------------------

INVALID_IDENTIFIER = ErrorCode(
    "SHIBA-3001",
    "INVALID_IDENTIFIER",
    "El identificador SQL no cumple el formato permitido.",
    SchemaError,
)
INVALID_OPERATOR = ErrorCode(
    "SHIBA-3002",
    "INVALID_OPERATOR",
    "Operador SQL no permitido.",
    SchemaError,
)
NO_COLUMNS_DEFINED = ErrorCode(
    "SHIBA-3003",
    "NO_COLUMNS_DEFINED",
    "No se han definido columnas en el esquema.",
    SchemaError,
)
TABLE_ALREADY_EXISTS = ErrorCode(
    "SHIBA-3004",
    "TABLE_ALREADY_EXISTS",
    "La tabla ya existe.",
    SchemaError,
)
DATABASE_ALREADY_EXISTS = ErrorCode(
    "SHIBA-3005",
    "DATABASE_ALREADY_EXISTS",
    "La base de datos ya existe.",
    SchemaError,
)
UNSUPPORTED_TYPE = ErrorCode(
    "SHIBA-3006",
    "UNSUPPORTED_TYPE",
    "El tipo de columna no está soportado por este dialecto.",
    SchemaError,
)

# --- SHIBA-4xxx — Integridad ------------------------------------------------

INTEGRITY_DUPLICATE_KEY = ErrorCode(
    "SHIBA-4001",
    "INTEGRITY_DUPLICATE_KEY",
    "Violación de clave única o primaria.",
    IntegrityError,
)
INTEGRITY_FOREIGN_KEY = ErrorCode(
    "SHIBA-4002",
    "INTEGRITY_FOREIGN_KEY",
    "Violación de restricción de clave foránea.",
    IntegrityError,
)
INTEGRITY_NOT_NULL = ErrorCode(
    "SHIBA-4003",
    "INTEGRITY_NOT_NULL",
    "Violación de NOT NULL.",
    IntegrityError,
)
INTEGRITY_CHECK = ErrorCode(
    "SHIBA-4004",
    "INTEGRITY_CHECK",
    "Violación de CHECK constraint.",
    IntegrityError,
)

# --- SHIBA-5xxx — Transacciones / concurrencia ------------------------------

DEADLOCK_DETECTED = ErrorCode(
    "SHIBA-5001",
    "DEADLOCK_DETECTED",
    "El servidor detectó un deadlock y abortó la transacción.",
    QueryError,
)
SERIALIZATION_FAILURE = ErrorCode(
    "SHIBA-5002",
    "SERIALIZATION_FAILURE",
    "La transacción no pudo serializarse y debe reintentarse.",
    QueryError,
)
NO_ACTIVE_TRANSACTION = ErrorCode(
    "SHIBA-5003",
    "NO_ACTIVE_TRANSACTION",
    "Operación de transacción sin transacción activa.",
    QueryError,
)
TRANSACTION_ALREADY_ACTIVE = ErrorCode(
    "SHIBA-5004",
    "TRANSACTION_ALREADY_ACTIVE",
    "Ya hay una transacción activa en esta conexión.",
    QueryError,
)

# --- SHIBA-6xxx — Datos / validación ----------------------------------------

MISSING_REQUIRED_DATA = ErrorCode(
    "SHIBA-6001",
    "MISSING_REQUIRED_DATA",
    "Faltan datos requeridos.",
    MissingDataError,
)
INVALID_DATA_FORMAT = ErrorCode(
    "SHIBA-6002",
    "INVALID_DATA_FORMAT",
    "Formato de datos inválido.",
    MissingDataError,
)

# --- SHIBA-9xxx — Genéricos -------------------------------------------------

UNKNOWN_ERROR = ErrorCode(
    "SHIBA-9001",
    "UNKNOWN_ERROR",
    "Error no clasificado.",
    ShibaError,
)
NOT_IMPLEMENTED = ErrorCode(
    "SHIBA-9999",
    "NOT_IMPLEMENTED",
    "Funcionalidad no implementada en este dialecto.",
    ShibaError,
)


# Registro indexable por código y por nombre (útil para serialización).
ALL_CODES: tuple[ErrorCode, ...] = tuple(
    v for v in globals().values() if isinstance(v, ErrorCode)
)
BY_CODE: Mapping[str, ErrorCode] = {c.code: c for c in ALL_CODES}
BY_NAME: Mapping[str, ErrorCode] = {c.name: c for c in ALL_CODES}


# --- Mapeo desde errores nativos del driver ---------------------------------

# Códigos numéricos MySQL/MariaDB → ErrorCode. Sólo los más comunes; el resto
# cae en QUERY_EXECUTION_FAILED.
# Ref: https://dev.mysql.com/doc/mysql-errors/8.0/en/server-error-reference.html
_MYSQL_ERRNO_MAP: dict[int, ErrorCode] = {
    1045: AUTH_FAILED,
    1049: UNKNOWN_TABLE,  # Unknown database (cercano)
    1051: UNKNOWN_TABLE,
    1054: UNKNOWN_COLUMN,
    1062: INTEGRITY_DUPLICATE_KEY,
    1064: QUERY_SYNTAX_ERROR,
    1146: UNKNOWN_TABLE,
    1213: DEADLOCK_DETECTED,
    1216: INTEGRITY_FOREIGN_KEY,
    1217: INTEGRITY_FOREIGN_KEY,
    1364: INTEGRITY_NOT_NULL,
    1451: INTEGRITY_FOREIGN_KEY,
    1452: INTEGRITY_FOREIGN_KEY,
    2002: CONNECTION_REFUSED,
    2003: CONNECTION_REFUSED,
    2006: CONNECTION_LOST,
    2013: CONNECTION_LOST,
    2059: AUTH_FAILED,
    3819: INTEGRITY_CHECK,
}


def from_driver_exception(exc: BaseException) -> ErrorCode:
    """Traduce una excepción nativa del driver a nuestro :class:`ErrorCode`.

    Si no se reconoce el error, devuelve :data:`QUERY_EXECUTION_FAILED`.
    """
    # pymysql usa `exc.args = (errno, msg)`; psycopg expone `.pgcode`.
    errno: int | None = None
    args = getattr(exc, "args", None)
    if args and isinstance(args, tuple) and args and isinstance(args[0], int):
        errno = args[0]

    if errno is not None and errno in _MYSQL_ERRNO_MAP:
        return _MYSQL_ERRNO_MAP[errno]

    # Heurística por nombre de clase para drivers que no exponen errno.
    name = type(exc).__name__
    if "IntegrityError" in name:
        return INTEGRITY_DUPLICATE_KEY
    if "OperationalError" in name:
        return CONNECTION_LOST
    if "ProgrammingError" in name:
        return QUERY_SYNTAX_ERROR
    if "InterfaceError" in name:
        return CONNECTION_NOT_OPEN

    return QUERY_EXECUTION_FAILED
