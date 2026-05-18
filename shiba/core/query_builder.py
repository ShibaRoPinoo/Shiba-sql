"""QueryBuilder fluido y agnóstico de dialecto.

Construye SQL con **placeholders parametrizados** para todos los valores
y delega quoting de identificadores al :class:`~shiba.dialects.base.Dialect`.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from shiba import error_codes
from shiba.identifiers import validate_identifier, validate_operator

_JSON_PATH_RE = re.compile(r"^\$(\.[A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\])+$")

if TYPE_CHECKING:
    from shiba.dialects.base import Dialect
    from shiba.dialects.mysql.driver import Database


_VALID_JOIN_TYPES = frozenset({"JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "CROSS JOIN"})


# Cada cláusula WHERE acumulada es (connector, sql_fragment, params).
# `connector` se ignora en la primera; las siguientes se concatenan con él.
_WhereItem = tuple[str, str, list[Any]]


class QueryBuilder:
    """API fluida para consultas. Cada método retorna ``self``."""

    def __init__(self, db: Database, table_name: str, *, dialect: Dialect) -> None:
        self.db = db
        self.dialect = dialect
        self.table_name = validate_identifier(table_name, kind="table")
        self._selected: list[str] = []
        self._joins: list[str] = []
        self._where: list[_WhereItem] = []
        self._group_by: list[str] = []
        self._having: list[_WhereItem] = []
        self._order_by: list[tuple[str, str]] = []
        self._limit: int | None = None
        self._offset: int | None = None

    # ------------------------------------------------------------------
    # SELECT
    # ------------------------------------------------------------------

    def select(self, *columns: str) -> QueryBuilder:
        if not columns:
            raise error_codes.MISSING_REQUIRED_DATA.build(
                "select() requiere al menos una columna."
            )
        for col in columns:
            validate_identifier(col, kind="column")
        self._selected.extend(columns)
        return self

    # ------------------------------------------------------------------
    # JOIN
    # ------------------------------------------------------------------

    def _add_join(
        self,
        kind: str,
        table_name: str,
        column1: str,
        operator: str,
        column2: str,
    ) -> QueryBuilder:
        if kind not in _VALID_JOIN_TYPES:
            raise error_codes.NOT_IMPLEMENTED.build(f"JOIN type no soportado: {kind}")
        if not all([table_name, column1, operator, column2]):
            raise error_codes.MISSING_REQUIRED_DATA.build(
                f"Faltan parámetros requeridos para {kind}."
            )
        t = self.dialect.quote_identifier(table_name)
        c1 = self.dialect.quote_identifier(column1)
        c2 = self.dialect.quote_identifier(column2)
        op = validate_operator(operator)
        self._joins.append(f"{kind} {t} ON {c1} {op} {c2}")
        return self

    def join(self, table_name: str, column1: str, operator: str, column2: str) -> QueryBuilder:
        return self._add_join("JOIN", table_name, column1, operator, column2)

    def inner_join(
        self, table_name: str, column1: str, operator: str, column2: str
    ) -> QueryBuilder:
        return self._add_join("INNER JOIN", table_name, column1, operator, column2)

    def left_join(
        self, table_name: str, column1: str, operator: str, column2: str
    ) -> QueryBuilder:
        return self._add_join("LEFT JOIN", table_name, column1, operator, column2)

    def right_join(
        self, table_name: str, column1: str, operator: str, column2: str
    ) -> QueryBuilder:
        return self._add_join("RIGHT JOIN", table_name, column1, operator, column2)

    def cross_join(self, table_name: str) -> QueryBuilder:
        if not table_name:
            raise error_codes.MISSING_REQUIRED_DATA.build("CROSS JOIN requiere tabla.")
        self._joins.append(f"CROSS JOIN {self.dialect.quote_identifier(table_name)}")
        return self

    # ------------------------------------------------------------------
    # WHERE — fragmentos atómicos
    # ------------------------------------------------------------------

    def _where_fragment(
        self, column: str, operator: str, value: Any
    ) -> tuple[str, list[Any]]:
        """Devuelve ``(sql, params)`` para una condición simple."""
        validate_identifier(column, kind="column")
        op = validate_operator(operator)
        col_sql = self.dialect.quote_identifier(column)
        if op in {"IN", "NOT IN"}:
            if not isinstance(value, (list, tuple)) or not value:
                raise error_codes.INVALID_QUERY_PARAMS.build(
                    f"{op} requiere lista/tupla no vacía."
                )
            placeholders = ", ".join([self.dialect.placeholder] * len(value))
            return f"{col_sql} {op} ({placeholders})", list(value)
        if op in {"IS", "IS NOT"} and value is None:
            return f"{col_sql} {op} NULL", []
        return f"{col_sql} {op} {self.dialect.placeholder}", [value]

    def _push_where(
        self,
        connector: str,
        column: str,
        operator: str,
        value: Any,
        *,
        target: list[_WhereItem] | None = None,
    ) -> None:
        sql, params = self._where_fragment(column, operator, value)
        (target if target is not None else self._where).append((connector, sql, params))

    # ------------------------------------------------------------------
    # WHERE — API pública
    # ------------------------------------------------------------------

    def where(self, *args: Any) -> QueryBuilder:
        """``where(col, val)``, ``where(col, op, val)`` o ``where([[...], [...]])``."""
        if len(args) == 1 and isinstance(args[0], list):
            return self._where_many(args[0])
        column, operator, value = _unpack_condition(args)
        self._push_where("AND", column, operator, value)
        return self

    def or_where(self, *args: Any) -> QueryBuilder:
        column, operator, value = _unpack_condition(args)
        self._push_where("OR", column, operator, value)
        return self

    def where_in(self, column: str, values: list[Any] | tuple[Any, ...]) -> QueryBuilder:
        self._push_where("AND", column, "IN", values)
        return self

    def where_not_in(
        self, column: str, values: list[Any] | tuple[Any, ...]
    ) -> QueryBuilder:
        self._push_where("AND", column, "NOT IN", values)
        return self

    def where_null(self, column: str) -> QueryBuilder:
        self._push_where("AND", column, "IS", None)
        return self

    def where_not_null(self, column: str) -> QueryBuilder:
        self._push_where("AND", column, "IS NOT", None)
        return self

    def where_like(self, column: str, pattern: str) -> QueryBuilder:
        self._push_where("AND", column, "LIKE", pattern)
        return self

    def where_json(
        self,
        column: str,
        path: str,
        value: Any,
        operator: str = "=",
    ) -> QueryBuilder:
        """Filtra por un campo dentro de una columna JSON.

        ``path`` se valida contra ``$.foo.bar`` / ``$[0]``; **no** se
        parametriza (es estructura, no valor) pero sí se restringe a un
        alfabeto seguro.
        """
        validate_identifier(column, kind="column")
        if not _JSON_PATH_RE.match(path):
            raise error_codes.INVALID_QUERY_PARAMS.build(
                f"path JSON inválido: {path!r}. Usa $.foo o $[0]."
            )
        op = validate_operator(operator)
        col_sql = self.dialect.quote_identifier(column)
        sql = (
            f"JSON_UNQUOTE(JSON_EXTRACT({col_sql}, '{path}')) "
            f"{op} {self.dialect.placeholder}"
        )
        self._where.append(("AND", sql, [value]))
        return self

    def where_between(self, column: str, low: Any, high: Any) -> QueryBuilder:
        validate_identifier(column, kind="column")
        col_sql = self.dialect.quote_identifier(column)
        ph = self.dialect.placeholder
        self._where.append(
            ("AND", f"{col_sql} BETWEEN {ph} AND {ph}", [low, high])
        )
        return self

    def where_group(self, callback: Callable[[QueryBuilder], None]) -> QueryBuilder:
        """Agrupa condiciones entre paréntesis. Útil para mezclar AND/OR.

        .. code-block:: python

            q.where("active", True).where_group(
                lambda g: g.where("role", "admin").or_where("role", "owner")
            )
        """
        sub = QueryBuilder(self.db, self.table_name, dialect=self.dialect)
        callback(sub)
        if not sub._where:
            return self
        group_sql, group_params = _compile_where_clause(sub._where, leading=False)
        self._where.append(("AND", f"({group_sql})", group_params))
        return self

    def _where_many(self, conditions: list[Any]) -> QueryBuilder:
        for cond in conditions:
            if not isinstance(cond, (list, tuple)):
                raise error_codes.INVALID_QUERY_PARAMS.build(
                    f"cada condición debe ser list/tuple, recibió {type(cond).__name__}."
                )
            column, operator, value = _unpack_condition(tuple(cond))
            self._push_where("AND", column, operator, value)
        return self

    # ------------------------------------------------------------------
    # GROUP BY / HAVING / ORDER / LIMIT
    # ------------------------------------------------------------------

    def group_by(self, *columns: str) -> QueryBuilder:
        if not columns:
            raise error_codes.MISSING_REQUIRED_DATA.build(
                "group_by() requiere al menos una columna."
            )
        for col in columns:
            validate_identifier(col, kind="column")
        self._group_by.extend(columns)
        return self

    def having(self, *args: Any) -> QueryBuilder:
        column, operator, value = _unpack_condition(args)
        sql, params = self._where_fragment(column, operator, value)
        self._having.append(("AND", sql, params))
        return self

    def order_by(self, column: str, direction: str = "ASC") -> QueryBuilder:
        validate_identifier(column, kind="column")
        d = direction.strip().upper()
        if d not in {"ASC", "DESC"}:
            raise error_codes.INVALID_QUERY_PARAMS.build(
                f"dirección inválida: {direction!r}. Use ASC o DESC."
            )
        self._order_by.append((column, d))
        return self

    def limit(self, n: int) -> QueryBuilder:
        self._limit = int(n)
        return self

    def offset(self, n: int) -> QueryBuilder:
        self._offset = int(n)
        return self

    # ------------------------------------------------------------------
    # Compilación
    # ------------------------------------------------------------------

    def _compile_where(self) -> tuple[str, list[Any]]:
        if not self._where:
            return "", []
        sql, params = _compile_where_clause(self._where, leading=True)
        return sql, params

    def _compile_having(self) -> str:
        if not self._having:
            return ""
        sql, _ = _compile_where_clause(self._having, leading=False)
        return "HAVING " + sql

    def _compile_select_clause(self) -> str:
        if not self._selected:
            return "*"
        return ", ".join(self.dialect.quote_identifier(c) for c in self._selected)

    def _compile_tail(self) -> tuple[str, list[Any]]:
        """Devuelve la SQL común WHERE+GROUP+HAVING+ORDER+LIMIT y sus params."""
        where_sql, params = self._compile_where()
        having_sql = self._compile_having()
        for _, _, p in self._having:
            params.extend(p)

        group_sql = ""
        if self._group_by:
            group_sql = "GROUP BY " + ", ".join(
                self.dialect.quote_identifier(c) for c in self._group_by
            )
        order_sql = ""
        if self._order_by:
            order_sql = "ORDER BY " + ", ".join(
                f"{self.dialect.quote_identifier(c)} {d}" for c, d in self._order_by
            )
        limit_sql = self.dialect.render_limit(self._limit, self._offset)
        tail = " ".join(p for p in [where_sql, group_sql, having_sql, order_sql, limit_sql] if p)
        return tail, params

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def get(self) -> list[dict[str, Any]]:
        select_clause = self._compile_select_clause()
        joins = " ".join(self._joins)
        tail, params = self._compile_tail()
        table = self.dialect.quote_identifier(self.table_name)
        query = " ".join(
            p for p in [f"SELECT {select_clause} FROM {table}", joins, tail] if p
        )
        return self.db.execute(query.strip(), tuple(params) if params else None)

    def first(self) -> dict[str, Any] | None:
        self._limit = 1
        rows = self.get()
        return rows[0] if rows else None

    def find(self, pk_value: Any, *, pk: str = "id") -> dict[str, Any] | None:
        return self.where(pk, pk_value).first()

    def exists(self) -> bool:
        return self.count() > 0

    def pluck(self, column: str) -> list[Any]:
        validate_identifier(column, kind="column")
        rows = self.select(column).get()
        return [row[column] for row in rows]

    def _aggregate(self, fn: str, column: str) -> Any:
        col = "*" if column == "*" else self.dialect.quote_identifier(column)
        joins = " ".join(self._joins)
        tail, params = self._compile_tail()
        table = self.dialect.quote_identifier(self.table_name)
        query = " ".join(
            p for p in [f"SELECT {fn}({col}) AS v FROM {table}", joins, tail] if p
        )
        rows = self.db.execute(query.strip(), tuple(params) if params else None)
        return rows[0]["v"] if rows else None

    def count(self, column: str = "*") -> int:
        result = self._aggregate("COUNT", column)
        return int(result) if result is not None else 0

    def sum(self, column: str) -> Any:
        return self._aggregate("SUM", column)

    def avg(self, column: str) -> Any:
        return self._aggregate("AVG", column)

    def min(self, column: str) -> Any:
        return self._aggregate("MIN", column)

    def max(self, column: str) -> Any:
        return self._aggregate("MAX", column)

    # ------------------------------------------------------------------
    # Paginación y streaming
    # ------------------------------------------------------------------

    def paginate(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """Devuelve ``{page, per_page, total, last_page, data}``."""
        if page < 1 or per_page < 1:
            raise error_codes.INVALID_QUERY_PARAMS.build(
                "paginate() exige page>=1 y per_page>=1."
            )
        total = QueryBuilder._clone_for_count(self).count()
        last_page = max(1, (total + per_page - 1) // per_page)
        self._limit = per_page
        self._offset = (page - 1) * per_page
        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "last_page": last_page,
            "data": self.get(),
        }

    @staticmethod
    def _clone_for_count(src: QueryBuilder) -> QueryBuilder:
        """Clon ligero que comparte WHERE/JOIN pero sin limit/offset/order."""
        clone = QueryBuilder(src.db, src.table_name, dialect=src.dialect)
        clone._joins = list(src._joins)
        clone._where = list(src._where)
        clone._group_by = list(src._group_by)
        clone._having = list(src._having)
        return clone

    def chunk(
        self,
        size: int,
        callback: Callable[[list[dict[str, Any]]], None],
        *,
        order_by_pk: str = "id",
    ) -> None:
        """Procesa la consulta en lotes de ``size`` filas.

        Pagina por ``OFFSET`` (suficiente para tablas medianas). Para
        tablas muy grandes usar :meth:`iterate` con cursor keyset.
        """
        if size < 1:
            raise error_codes.INVALID_QUERY_PARAMS.build("chunk size debe ser >= 1.")
        offset = 0
        while True:
            clone = QueryBuilder._clone_for_count(self)
            clone._order_by = list(self._order_by) or [(order_by_pk, "ASC")]
            clone._limit = size
            clone._offset = offset
            batch = clone.get()
            if not batch:
                return
            callback(batch)
            if len(batch) < size:
                return
            offset += size

    def iterate(
        self,
        chunk_size: int = 1000,
        *,
        order_by_pk: str = "id",
    ) -> Iterator[dict[str, Any]]:
        """Generator que recorre toda la consulta por lotes."""
        batches: list[list[dict[str, Any]]] = []
        self.chunk(chunk_size, batches.append, order_by_pk=order_by_pk)
        for batch in batches:
            yield from batch

    # ------------------------------------------------------------------
    # INSERT / UPDATE / DELETE / UPSERT
    # ------------------------------------------------------------------

    def insert(self, data: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return self._insert_many(data)
        if isinstance(data, dict):
            return self._insert_single(data)
        raise error_codes.INVALID_DATA_FORMAT.build(
            f"insert() acepta dict o list[dict], recibió {type(data).__name__}."
        )

    def _insert_single(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        if not data:
            raise error_codes.MISSING_REQUIRED_DATA.build("insert(): dict vacío.")
        cols = [validate_identifier(k, kind="column") for k in data]
        cols_sql = ", ".join(self.dialect.quote_identifier(c) for c in cols)
        placeholders = ", ".join([self.dialect.placeholder] * len(cols))
        table = self.dialect.quote_identifier(self.table_name)
        query = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"
        return self.db.execute(query, tuple(data.values()))

    def _insert_many(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        first_keys = list(rows[0].keys())
        if not first_keys:
            raise error_codes.MISSING_REQUIRED_DATA.build("insert(): filas vacías.")
        cols = [validate_identifier(k, kind="column") for k in first_keys]
        values: list[tuple[Any, ...]] = []
        for row in rows:
            if list(row.keys()) != first_keys:
                raise error_codes.INVALID_DATA_FORMAT.build(
                    "insert(): todas las filas deben tener las mismas claves "
                    "en el mismo orden."
                )
            values.append(tuple(row[k] for k in first_keys))
        cols_sql = ", ".join(self.dialect.quote_identifier(c) for c in cols)
        placeholders = ", ".join([self.dialect.placeholder] * len(cols))
        table = self.dialect.quote_identifier(self.table_name)
        query = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"
        return self.db.execute(query, values, many=True)

    def upsert(
        self,
        data: dict[str, Any],
        *,
        update: list[str] | None = None,
        on: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """INSERT con resolución de conflicto.

        :param data: columnas → valores.
        :param update: columnas a pisar en conflicto (default todas).
        :param on: columnas del conflicto. Requerido por Postgres,
            opcional en MySQL (lo detecta por la PK).
        """
        if not data:
            raise error_codes.MISSING_REQUIRED_DATA.build("upsert(): dict vacío.")
        cols = [validate_identifier(k, kind="column") for k in data]
        cols_sql = ", ".join(self.dialect.quote_identifier(c) for c in cols)
        placeholders = ", ".join([self.dialect.placeholder] * len(cols))
        update_cols = update if update is not None else list(data.keys())
        for col in update_cols:
            validate_identifier(col, kind="column")
        for col in on or []:
            validate_identifier(col, kind="column")
        update_sql = self.dialect.compile_upsert_update(update_cols, on)
        table = self.dialect.quote_identifier(self.table_name)
        query = (
            f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) {update_sql}"
        )
        return self.db.execute(query, tuple(data.values()))

    def update(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        if not data:
            raise error_codes.MISSING_REQUIRED_DATA.build("update() requiere datos.")
        set_parts: list[str] = []
        params: list[Any] = []
        for col, val in data.items():
            validate_identifier(col, kind="column")
            set_parts.append(
                f"{self.dialect.quote_identifier(col)} = {self.dialect.placeholder}"
            )
            params.append(val)
        where_sql, where_params = self._compile_where()
        params.extend(where_params)
        table = self.dialect.quote_identifier(self.table_name)
        query = f"UPDATE {table} SET {', '.join(set_parts)} {where_sql}".strip()
        return self.db.execute(query, tuple(params))

    def delete(self) -> list[dict[str, Any]]:
        where_sql, params = self._compile_where()
        if not where_sql:
            raise error_codes.MISSING_REQUIRED_DATA.build(
                "delete() sin WHERE no está permitido. Usa truncate() si quieres vaciar."
            )
        table = self.dialect.quote_identifier(self.table_name)
        query = f"DELETE FROM {table} {where_sql}".strip()
        return self.db.execute(query, tuple(params))

    def truncate(self) -> list[dict[str, Any]]:
        """``TRUNCATE TABLE`` — borra todas las filas y resetea AUTO_INCREMENT."""
        table = self.dialect.quote_identifier(self.table_name)
        return self.db.execute(f"TRUNCATE TABLE {table}")


# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------

def _unpack_condition(args: tuple[Any, ...]) -> tuple[str, str, Any]:
    if len(args) == 2:
        return args[0], "=", args[1]
    if len(args) == 3:
        return args[0], args[1], args[2]
    raise error_codes.INVALID_QUERY_PARAMS.build(
        f"se esperaban 2 o 3 argumentos, llegaron {len(args)}."
    )


def _compile_where_clause(
    items: list[_WhereItem], *, leading: bool
) -> tuple[str, list[Any]]:
    parts: list[str] = []
    params: list[Any] = []
    for idx, (connector, sql, p) in enumerate(items):
        if idx == 0:
            parts.append(sql)
        else:
            parts.append(f"{connector} {sql}")
        params.extend(p)
    body = " ".join(parts)
    return (f"WHERE {body}", params) if leading else (body, params)
