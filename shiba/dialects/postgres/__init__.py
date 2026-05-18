"""Dialecto PostgreSQL."""
from typing import Any

from shiba.dialects.postgres.dialect import PostgresDialect

__all__ = ["PostgresDialect"]


def _import_driver() -> Any:
    """Import perezoso de ``Database`` (requiere ``psycopg``)."""
    from shiba.dialects.postgres.driver import Database

    return Database


def __getattr__(name: str) -> Any:
    if name == "Database":
        return _import_driver()
    raise AttributeError(name)
