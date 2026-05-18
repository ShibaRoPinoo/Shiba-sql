"""Mapeo de tipos canónicos Shiba a SQL Postgres.

El ``TableBuilder`` emite sintaxis estilo MySQL (``DATETIME``,
``BOOLEAN``, ``JSON``, ``BLOB``, etc.). Este módulo los traduce a la
forma idiomática de Postgres.
"""
from __future__ import annotations

_MAPPING: dict[str, str] = {
    "DATETIME": "TIMESTAMP",
    "BLOB": "BYTEA",
    "JSON": "JSONB",
    "DOUBLE": "DOUBLE PRECISION",
}


def map_type(declared: str) -> str:
    upper = declared.upper()
    # Tipos con parámetros: ``VARCHAR(50)``, ``DECIMAL(10,2)``, etc.
    if "(" in upper:
        base, params = upper.split("(", 1)
        base = base.strip()
        if base in _MAPPING:
            return f"{_MAPPING[base]}({params}"
        return declared
    return _MAPPING.get(upper, declared)
