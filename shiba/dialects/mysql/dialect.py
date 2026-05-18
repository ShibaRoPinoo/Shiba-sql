"""Implementación :class:`~shiba.dialects.base.Dialect` para MySQL/MariaDB."""
from __future__ import annotations

from shiba.dialects.base import Dialect
from shiba.dialects.mysql.quoting import quote_identifier as _qi
from shiba.dialects.mysql.schema import map_type as _map_type


class MySQLDialect(Dialect):
    """Backticks, placeholder ``%s``, sintaxis ``LIMIT n OFFSET m``."""

    name = "mysql"
    placeholder = "%s"

    def quote_identifier(self, name: str) -> str:
        return _qi(name)

    def map_type(self, declared: str) -> str:
        return _map_type(declared)

    def compile_upsert_update(self, update_columns: list[str]) -> str:
        if not update_columns:
            return ""
        parts = [f"{_qi(c)} = VALUES({_qi(c)})" for c in update_columns]
        return "ON DUPLICATE KEY UPDATE " + ", ".join(parts)
