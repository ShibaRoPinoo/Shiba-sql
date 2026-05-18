"""Wrapper sobre :mod:`pymysql` con manejo de errores Shiba.

Diseño
------
* No comparte cursor entre operaciones — cada ``execute`` abre el suyo.
* Las transacciones se gestionan con ``Database.transaction()`` como
  context manager; fuera de una transacción cada operación auto-commit.
* Cualquier ``pymysql`` exception se traduce a un
  :class:`~shiba.errors.ShibaError` con su :class:`ErrorCode`.
* Nada de ``print`` — sólo ``logging``.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pymysql
import pymysql.cursors

from shiba import error_codes
from shiba.dialects.mysql.quoting import quote_identifier
from shiba.error_codes import from_driver_exception
from shiba.errors import QueryError

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger("shiba.mysql")


class Database:
    """Conexión MySQL con API estable de Shiba."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        database: str | None = None,
        charset: str = "utf8mb4",
        autoconnect: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self._connection: pymysql.connections.Connection | None = None
        self._in_transaction: bool = False
        if autoconnect:
            self.connect()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Abre la conexión. Idempotente."""
        if self._connection is not None and self._connection.open:
            return
        try:
            self._connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
        except pymysql.err.OperationalError as exc:
            code = from_driver_exception(exc)
            raise code.build(
                f"No se pudo conectar a {self.host}:{self.port}: {exc}",
                details={"host": self.host, "port": self.port},
            ) from exc
        except Exception as exc:  # pragma: no cover - defensivo
            raise error_codes.UNKNOWN_ERROR.build(
                f"Error inesperado al conectar: {exc}",
            ) from exc

    def close(self) -> None:
        """Cierra la conexión si está abierta."""
        if self._connection is not None and self._connection.open:
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

    # ------------------------------------------------------------------
    # Acceso interno seguro a la conexión
    # ------------------------------------------------------------------

    @property
    def _conn(self) -> pymysql.connections.Connection:
        if self._connection is None or not self._connection.open:
            raise error_codes.CONNECTION_NOT_OPEN.build(
                "La conexión no está abierta. ¿Llamaste a close() ya?"
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
        """Ejecuta ``query`` y devuelve filas (vacío si no hay rowset).

        Hace commit automático salvo que haya una transacción activa.
        """
        if not query or not isinstance(query, str):
            raise error_codes.EMPTY_QUERY.build(
                "Se intentó ejecutar una query vacía o no string.",
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
                except pymysql.err.Error:
                    rows = []
            if not self._in_transaction:
                conn.commit()
            return rows
        except pymysql.err.IntegrityError as exc:
            self._rollback_silent()
            code = from_driver_exception(exc)
            raise code.build(
                f"Violación de integridad: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc
        except pymysql.err.ProgrammingError as exc:
            self._rollback_silent()
            code = from_driver_exception(exc)
            raise code.build(
                f"Error de SQL: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc
        except pymysql.err.OperationalError as exc:
            self._rollback_silent()
            code = from_driver_exception(exc)
            raise code.build(
                f"Error operacional: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc
        except pymysql.err.Error as exc:
            self._rollback_silent()
            code = from_driver_exception(exc)
            raise code.build(
                f"Error de driver: {exc}",
                query=query,
                params=params,
                cause=exc,
            ) from exc

    # Alias retro-compatible con la API v1.x.
    execute_query = execute

    def _rollback_silent(self) -> None:
        if self._connection is None or not self._connection.open:
            return
        try:
            self._connection.rollback()
        except pymysql.err.Error:  # pragma: no cover - best effort
            logger.warning("rollback failed", exc_info=True)

    # ------------------------------------------------------------------
    # Transacciones
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        """Bloque transaccional. Commit al salir, rollback en excepción.

        No anidable en esta versión (se reservará para savepoints en
        Fase 4). Lanza :data:`error_codes.TRANSACTION_ALREADY_ACTIVE`
        si ya hay una activa.
        """
        if self._in_transaction:
            raise error_codes.TRANSACTION_ALREADY_ACTIVE.build()
        conn = self._conn
        conn.begin()
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
    # DDL/DML conveniencia
    # ------------------------------------------------------------------

    def create_database(self, name: str) -> Database:
        """``CREATE DATABASE IF NOT EXISTS`` validando el nombre."""
        try:
            self.execute(f"CREATE DATABASE IF NOT EXISTS {quote_identifier(name)}")
        except QueryError as exc:
            if exc.code is error_codes.INTEGRITY_DUPLICATE_KEY:
                logger.info("database %s already exists", name)
            else:
                raise
        self.database = name
        return self

    def use_database(self, name: str) -> Database:
        """``USE <name>`` validando el nombre."""
        self.execute(f"USE {quote_identifier(name)}")
        self.database = name
        return self

    # Alias retro-compatible.
    selected_database = use_database
