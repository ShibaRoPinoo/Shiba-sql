"""Mapeo de tipos canónicos a SQL MySQL.

Las declaraciones que produce :mod:`shiba.core.table_builder` ya son
sintaxis MySQL nativa (``VARCHAR(n)``, ``JSON``, ``DECIMAL(p,s)``), por
lo que este mapper es prácticamente identidad. La función existe para
que otros dialectos puedan traducir.
"""
from __future__ import annotations

# Tipos canónicos aceptados por Shiba. Si el TableBuilder produce un
# tipo fuera de esta lista, el dialecto lo emitirá tal cual pero se
# considera "no soportado" para fines de validación.
SUPPORTED_TYPES: frozenset[str] = frozenset(
    {
        "INT",
        "BIGINT",
        "TINYINT",
        "SMALLINT",
        "VARCHAR",
        "TEXT",
        "CHAR",
        "DATE",
        "DATETIME",
        "TIME",
        "TIMESTAMP",
        "DECIMAL",
        "FLOAT",
        "DOUBLE",
        "BOOLEAN",
        "BLOB",
        "ENUM",
        "JSON",
    }
)


def map_type(declared: str) -> str:
    """Identidad para MySQL. Punto de extensión para otros dialectos."""
    return declared
