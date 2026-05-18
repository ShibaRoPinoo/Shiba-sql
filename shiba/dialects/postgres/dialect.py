"""Implementación :class:`~shiba.dialects.base.Dialect` para PostgreSQL."""
from __future__ import annotations

from shiba import error_codes
from shiba.dialects.base import Dialect
from shiba.dialects.postgres.quoting import quote_identifier as _qi
from shiba.dialects.postgres.schema import map_type as _map_type


class PostgresDialect(Dialect):
    """Doble comillas, placeholder ``%s`` (psycopg), ``ON CONFLICT``."""

    name = "postgres"
    placeholder = "%s"

    def quote_identifier(self, name: str) -> str:
        return _qi(name)

    def map_type(self, declared: str) -> str:
        return _map_type(declared)

    def compile_auto_increment_pk(self, column_quoted: str) -> str:
        return f"{column_quoted} INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"

    def compile_upsert_update(
        self,
        update_columns: list[str],
        conflict_columns: list[str] | None = None,
    ) -> str:
        if not conflict_columns:
            error_codes.MISSING_REQUIRED_DATA.raise_(
                "upsert() en Postgres requiere el parámetro `on=[col, ...]` "
                "para identificar el conflicto."
            )
        target = ", ".join(_qi(c) for c in conflict_columns)
        if not update_columns:
            return f"ON CONFLICT ({target}) DO NOTHING"
        sets = ", ".join(f"{_qi(c)} = EXCLUDED.{_qi(c)}" for c in update_columns)
        return f"ON CONFLICT ({target}) DO UPDATE SET {sets}"
