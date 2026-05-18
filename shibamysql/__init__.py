"""Shim de compatibilidad con la API ``shibamysql`` v1.x.

Re-exporta los símbolos públicos desde :mod:`shiba`. Programar contra
este módulo emite :class:`DeprecationWarning`; migrar a ``import shiba``.
"""
from __future__ import annotations

import warnings

from shiba import (
    ConnectionError,
    Database,
    IntegrityError,
    MissingDataError,
    QueryBuilder,
    QueryError,
    SchemaError,
    ShibaConnection,
    ShibaError,
    TableBuilder,
    error_codes,
)

warnings.warn(
    "`shibamysql` está deprecado desde v2.0; importa desde `shiba` en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ConnectionError",
    "Database",
    "IntegrityError",
    "MissingDataError",
    "QueryBuilder",
    "QueryError",
    "SchemaError",
    "ShibaConnection",
    "ShibaError",
    "TableBuilder",
    "error_codes",
]
