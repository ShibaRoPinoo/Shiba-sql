"""Shiba — librería ligera para hablar con bases de datos relacionales.

Punto de entrada público:

.. code-block:: python

    import shiba as s

    with s.ShibaConnection(host="localhost", port=3306,
                           user="u", password="p") as cx:
        cx.create_database("my_db")
        cx.use_database("my_db")
        cx.create_table("users") \\
            .increments("id", primary_key=True) \\
            .string("name") \\
            .build()

        cx.table("users").insert({"name": "John"})
        rows = cx.table("users").where("name", "John").get()
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

from shiba import error_codes
from shiba.core.query_builder import QueryBuilder
from shiba.core.table_builder import TableBuilder
from shiba.dialects.mysql import Database, MySQLDialect
from shiba.errors import (
    ConnectionError,
    IntegrityError,
    MissingDataError,
    QueryError,
    SchemaError,
    ShibaError,
)

if TYPE_CHECKING:
    from types import TracebackType


class ShibaConnection:
    """Fachada de alto nivel sobre un :class:`Database` MySQL."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        database: str | None = None,
    ) -> None:
        self.dialect = MySQLDialect()
        self.db = Database(host, port, user, password, database=database)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> ShibaConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def create_database(self, database: str) -> Database:
        return self.db.create_database(database)

    def use_database(self, database: str) -> Database:
        return self.db.use_database(database)

    def create_table(self, table_name: str) -> TableBuilder:
        return TableBuilder(self.db, table_name, dialect=self.dialect)

    def table(self, table_name: str) -> QueryBuilder:
        return QueryBuilder(self.db, table_name, dialect=self.dialect)

    def transaction(self) -> AbstractContextManager[Database]:
        """Context manager transaccional. Ver :meth:`Database.transaction`."""
        return self.db.transaction()

    def raw(
        self,
        query: str,
        params: object = None,
        *,
        many: bool = False,
    ) -> list[dict[str, object]]:
        """Escape hatch — ver :meth:`Database.raw`."""
        return self.db.raw(query, params, many=many)


__all__ = [
    "ConnectionError",
    "Database",
    "IntegrityError",
    "MissingDataError",
    "MySQLDialect",
    "QueryBuilder",
    "QueryError",
    "SchemaError",
    "ShibaConnection",
    "ShibaError",
    "TableBuilder",
    "error_codes",
]
