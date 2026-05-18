"""QueryBuilder fluido y agnóstico de dialecto.

Construye SQL con **placeholders parametrizados** para todos los valores
y delega quoting de identificadores al :class:`~shiba.dialects.base.Dialect`.
Esto cierra el agujero de SQL injection que tenía la v1.x.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shiba import error_codes
from shiba.identifiers import validate_identifier, validate_operator

if TYPE_CHECKING:
    from shiba.dialects.base import Dialect
    from shiba.dialects.mysql.driver import Database


_VALID_JOIN_TYPES = frozenset({"JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "CROSS JOIN"})


class QueryBuilder:
    """API fluida para consultas. Inmutable-ish: cada método retorna ``self``."""

    def __init__(self, db: Database, table_name: str, *, dialect: Dialect) -> None:
        self.db = db
        self.dialect = dialect
        self.table_name = validate_identifier(table_name, kind="table")
        self._selected: list[str] = []
        self._joins: list[str] = []
        self._where: list[tuple[str, str, Any]] = []
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
    # WHERE
    # ------------------------------------------------------------------

    def where(self, *args: Any) -> QueryBuilder:
        """``where(col, val)`` o ``where(col, op, val)`` o ``where([[...], [...]])``."""
        # Forma con lista de condiciones.
        if len(args) == 1 and isinstance(args[0], list):
            return self._where_many(args[0])

        if len(args) == 2:
            column, value = args
            operator = "="
        elif len(args) == 3:
            column, operator, value = args
        else:
            raise error_codes.INVALID_QUERY_PARAMS.build(
                f"where() acepta 2 o 3 argumentos, recibió {len(args)}."
            )

        validate_identifier(column, kind="column")
        op = validate_operator(operator)
        self._where.append((column, op, value))
        return self

    def _where_many(self, conditions: list[Any]) -> QueryBuilder:
        for cond in conditions:
            if not isinstance(cond, (list, tuple)):
                raise error_codes.INVALID_QUERY_PARAMS.build(
                    f"cada condición de where() debe ser list/tuple, recibió {type(cond).__name__}."
                )
            if len(cond) == 2:
                self.where(cond[0], cond[1])
            elif len(cond) == 3:
                self.where(cond[0], cond[1], cond[2])
            else:
                raise error_codes.INVALID_QUERY_PARAMS.build(
                    f"condición con {len(cond)} elementos; se esperaban 2 o 3."
                )
        return self

    # ------------------------------------------------------------------
    # ORDER / LIMIT
    # ------------------------------------------------------------------

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
    # Compilación de WHERE
    # ------------------------------------------------------------------

    def _compile_where(self) -> tuple[str, list[Any]]:
        if not self._where:
            return "", []
        parts: list[str] = []
        params: list[Any] = []
        for column, op, value in self._where:
            col_sql = self.dialect.quote_identifier(column)
            if op in {"IN", "NOT IN"}:
                if not isinstance(value, (list, tuple)) or not value:
                    raise error_codes.INVALID_QUERY_PARAMS.build(
                        f"{op} requiere lista/tupla no vacía."
                    )
                placeholders = ", ".join([self.dialect.placeholder] * len(value))
                parts.append(f"{col_sql} {op} ({placeholders})")
                params.extend(value)
            elif op in {"IS", "IS NOT"} and value is None:
                parts.append(f"{col_sql} {op} NULL")
            else:
                parts.append(f"{col_sql} {op} {self.dialect.placeholder}")
                params.append(value)
        return "WHERE " + " AND ".join(parts), params

    # ------------------------------------------------------------------
    # SELECT execution
    # ------------------------------------------------------------------

    def get(self) -> list[dict[str, Any]]:
        select_clause = "*"
        if self._selected:
            select_clause = ", ".join(self.dialect.quote_identifier(c) for c in self._selected)

        joins = " ".join(self._joins)
        where_sql, params = self._compile_where()

        order_sql = ""
        if self._order_by:
            order_sql = "ORDER BY " + ", ".join(
                f"{self.dialect.quote_identifier(c)} {d}" for c, d in self._order_by
            )
        limit_sql = self.dialect.render_limit(self._limit, self._offset)

        table = self.dialect.quote_identifier(self.table_name)
        parts = [f"SELECT {select_clause} FROM {table}", joins, where_sql, order_sql, limit_sql]
        query = " ".join(p for p in parts if p).strip()
        return self.db.execute(query, tuple(params) if params else None)

    def first(self) -> dict[str, Any] | None:
        self._limit = 1
        rows = self.get()
        return rows[0] if rows else None

    def count(self, column: str = "*") -> int:
        col = "*" if column == "*" else self.dialect.quote_identifier(column)
        joins = " ".join(self._joins)
        where_sql, params = self._compile_where()
        table = self.dialect.quote_identifier(self.table_name)
        query = f"SELECT COUNT({col}) AS cnt FROM {table} {joins} {where_sql}".strip()
        rows = self.db.execute(query, tuple(params) if params else None)
        return int(rows[0]["cnt"]) if rows else 0

    # ------------------------------------------------------------------
    # INSERT / UPDATE / DELETE
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
        # Forzamos que todas las filas tengan las mismas claves y en el mismo orden.
        values: list[tuple[Any, ...]] = []
        for row in rows:
            if list(row.keys()) != first_keys:
                raise error_codes.INVALID_DATA_FORMAT.build(
                    "insert(): todas las filas deben tener las mismas claves en el mismo orden."
                )
            values.append(tuple(row[k] for k in first_keys))
        cols_sql = ", ".join(self.dialect.quote_identifier(c) for c in cols)
        placeholders = ", ".join([self.dialect.placeholder] * len(cols))
        table = self.dialect.quote_identifier(self.table_name)
        query = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"
        return self.db.execute(query, values, many=True)

    def update(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        if not data:
            raise error_codes.MISSING_REQUIRED_DATA.build("update() requiere datos.")
        set_parts: list[str] = []
        params: list[Any] = []
        for col, val in data.items():
            validate_identifier(col, kind="column")
            set_parts.append(f"{self.dialect.quote_identifier(col)} = {self.dialect.placeholder}")
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
