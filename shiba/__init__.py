"""Shiba — librería ligera para hablar con bases de datos relacionales.

.. code-block:: python

    import shiba

    # Forma 1 — DSN explícito (recomendado para multi-dialecto):
    cx = shiba.connect("mysql://user:pass@localhost:3306/my_db")
    cx = shiba.connect("postgres://user:pass@localhost:5432/my_db")

    # Forma 2 — construcción directa MySQL (legacy):
    cx = shiba.ShibaConnection(host="localhost", port=3306,
                               user="u", password="p")
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from shiba import error_codes
from shiba.core.query_builder import QueryBuilder
from shiba.core.table_builder import TableBuilder
from shiba.dialects.base import Dialect
from shiba.dialects.mysql import Database, MySQLDialect
from shiba.errors import (
    ConnectionError,
    IntegrityError,
    MissingDataError,
    QueryError,
    SchemaError,
    ShibaError,
)
from shiba.orm import Model, fields, set_default_connection

if TYPE_CHECKING:
    from types import TracebackType


class ShibaConnection:
    """Fachada de alto nivel agnóstica de dialecto.

    Acepta dos formas de construcción:

    * Legacy MySQL: ``ShibaConnection(host, port, user, password)``.
    * Inyectada: ``ShibaConnection(db=Database(...), dialect=Dialect(...))``
      (la usa :func:`connect`).
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        *,
        database: str | None = None,
        db: Any = None,
        dialect: Dialect | None = None,
    ) -> None:
        if db is not None and dialect is not None:
            self.dialect: Dialect = dialect
            self.db: Any = db
            return

        if host is None or port is None or user is None or password is None:
            error_codes.MISSING_REQUIRED_DATA.raise_(
                "ShibaConnection requiere host/port/user/password o "
                "db+dialect inyectados."
            )
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

    def create_database(self, database: str) -> Any:
        return self.db.create_database(database)

    def use_database(self, database: str) -> Any:
        return self.db.use_database(database)

    def create_table(self, table_name: str) -> TableBuilder:
        return TableBuilder(self.db, table_name, dialect=self.dialect)

    def table(self, table_name: str) -> QueryBuilder:
        return QueryBuilder(self.db, table_name, dialect=self.dialect)

    def transaction(self) -> AbstractContextManager[Any]:
        """Context manager transaccional."""
        cm: AbstractContextManager[Any] = self.db.transaction()
        return cm

    def raw(
        self,
        query: str,
        params: object = None,
        *,
        many: bool = False,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = self.db.raw(query, params, many=many)
        return rows


# ---------------------------------------------------------------------------
# Factory connect(dsn)
# ---------------------------------------------------------------------------


_DEFAULT_PORTS = {"mysql": 3306, "postgres": 5432, "postgresql": 5432}


def connect(dsn: str) -> ShibaConnection:
    """Construye una :class:`ShibaConnection` desde un DSN tipo URL.

    Schemes soportados:

    * ``mysql://user:pass@host:port/dbname``
    * ``postgres://user:pass@host:port/dbname`` (alias: ``postgresql://``)
    """
    parsed = urlparse(dsn)
    scheme = parsed.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        error_codes.NOT_IMPLEMENTED.raise_(
            f"DSN scheme '{scheme}' no soportado. Usa: {sorted(_DEFAULT_PORTS)}."
        )
    host = parsed.hostname or "localhost"
    port = parsed.port or _DEFAULT_PORTS[scheme]
    user = parsed.username or ""
    password = parsed.password or ""
    database = parsed.path.lstrip("/") or None

    if scheme == "mysql":
        db: Any = Database(host, port, user, password, database=database)
        return ShibaConnection(db=db, dialect=MySQLDialect())

    # postgres / postgresql
    from shiba.dialects.postgres import PostgresDialect
    from shiba.dialects.postgres.driver import Database as PgDatabase

    db = PgDatabase(host, port, user, password, database=database)
    return ShibaConnection(db=db, dialect=PostgresDialect())

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
    "Dialect",
    "IntegrityError",
    "MissingDataError",
    "Model",
    "MySQLDialect",
    "QueryBuilder",
    "QueryError",
    "SchemaError",
    "ShibaConnection",
    "ShibaError",
    "TableBuilder",
    "connect",
    "error_codes",
    "fields",
    "set_default_connection",
]
