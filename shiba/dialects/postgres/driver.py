"""Wrapper sobre :mod:`psycopg` (v3) con la interfaz Shiba ``Database``."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from shiba import error_codes
from shiba.dialects.postgres.quoting import quote_identifier
from shiba.error_codes import from_driver_exception

if TYPE_CHECKING:
    from types import TracebackType

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - dep opcional
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]


def _require_psycopg() -> None:
    if psycopg is None:
        raise ImportError(
            "El dialecto Postgres requiere `psycopg[binary]`. "
            "Instala: pip install 'shiba_mysql[postgres]' o psycopg[binary]"
        )


logger = logging.getLogger("shiba.postgres")


class Database:
    """Conexión Postgres con la misma API que :class:`shiba.Database` de MySQL."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        database: str | None = None,
        autoconnect: bool = True,
    ) -> None:
        _require_psycopg()
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self._connection: Any = None
        self._in_transaction: bool = False
        if autoconnect:
            self.connect()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def connect(self) -> None:
        if self._connection is not None and not self._connection.closed:
            return
        try:
            self._connection = psycopg.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.database,
                autocommit=True,
                row_factory=dict_row,
            )
        except psycopg.OperationalError as exc:
            code = from_driver_exception(exc)
            raise code.build(
                f"No se pudo conectar a {self.host}:{self.port}: {exc}",
                details={"host": self.host, "port": self.port},
            ) from exc

    def close(self) -> None:
        if self._connection is not None and not self._connection.closed:
            self._connection.close()
        self._connection = None
        self._in_transaction = False

    def __enter__(self) -> Database:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def _conn(self) -> Any:
        if self._connection is None or self._connection.closed:
            raise error_codes.CONNECTION_NOT_OPEN.build(
                "La conexión Postgres no está abierta."
            )
        return self._connection

    # ------------------------------------------------------------------
    # Ejecución
    # ------------------------------------------------------------------

    def execute(
        self,
        query: str,
        params: Any = None,
        *,
        many: bool = False,
    ) -> list[dict[str, Any]]:
        if not query or not isinstance(query, str):
            raise error_codes.EMPTY_QUERY.build(
                "Se intentó ejecutar una query vacía.",
                query=str(query),
            )
        conn = self._conn
        try:
            with conn.cursor() as cursor:
                if params is None:
                    cursor.execute(query)
                elif many:
                    cursor.executemany(query, params)
                else:
                    cursor.execute(query, params)
                try:
                    rows: list[dict[str, Any]] = list(cursor.fetchall())
                except psycopg.ProgrammingError:
                    rows = []
            if not self._in_transaction:
                conn.commit()
            return rows
        except psycopg.errors.IntegrityError as exc:
            self._rollback_silent()
            code = from_driver_exception(exc)
            raise code.build(
                f"Violación de integridad: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc
        except psycopg.errors.SyntaxError as exc:
            self._rollback_silent()
            raise error_codes.QUERY_SYNTAX_ERROR.build(
                f"Error de sintaxis: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc
        except psycopg.OperationalError as exc:
            self._rollback_silent()
            code = from_driver_exception(exc)
            raise code.build(
                f"Error operacional: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc
        except psycopg.Error as exc:
            self._rollback_silent()
            code = from_driver_exception(exc)
            raise code.build(
                f"Error de driver: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc

    execute_query = execute

    def raw(
        self,
        query: str,
        params: Any = None,
        *,
        many: bool = False,
    ) -> list[dict[str, Any]]:
        return self.execute(query, params, many=many)

    def _rollback_silent(self) -> None:
        if self._connection is None or self._connection.closed:
            return
        try:
            self._connection.rollback()
        except psycopg.Error:  # pragma: no cover - best effort
            logger.warning("rollback failed", exc_info=True)

    # ------------------------------------------------------------------
    # Transacciones
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        if self._in_transaction:
            raise error_codes.TRANSACTION_ALREADY_ACTIVE.build()
        conn = self._conn
        # En psycopg3 autocommit=True implica BEGIN explícito para abrir tx.
        conn.execute("BEGIN")
        self._in_transaction = True
        try:
            yield self
        except BaseException:
            self._rollback_silent()
            raise
        else:
            conn.commit()
        finally:
            self._in_transaction = False

    # ------------------------------------------------------------------
    # DDL conveniencia
    # ------------------------------------------------------------------

    def create_database(self, name: str) -> Database:
        try:
            self.execute(f"CREATE DATABASE {quote_identifier(name)}")
        except Exception as exc:  # pragma: no cover - mensajes varían
            if "already exists" not in str(exc):
                raise
        self.database = name
        return self

    def use_database(self, name: str) -> Database:
        """En Postgres no hay ``USE``. Se cierra y reconecta a la nueva DB."""
        self.close()
        self.database = name
        self.connect()
        return self

    selected_database = use_database
