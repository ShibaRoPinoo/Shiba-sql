"""TableBuilder fluido y agnóstico de dialecto.

Acumula declaraciones de columnas y constraints; ``build()`` compila el
``CREATE TABLE`` final delegando quoting y mapeo de tipos al
:class:`~shiba.dialects.base.Dialect`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from shiba import error_codes
from shiba.identifiers import validate_identifier

if TYPE_CHECKING:
    from shiba.dialects.base import Dialect
    from shiba.dialects.mysql.driver import Database


def _escape_enum_choice(choice: str) -> str:
    """Escapa una opción de ``ENUM`` duplicando comillas simples."""
    if not isinstance(choice, str):
        raise error_codes.INVALID_DATA_FORMAT.build(
            f"ENUM choice debe ser str, recibió {type(choice).__name__}."
        )
    return "'" + choice.replace("'", "''") + "'"


class TableBuilder:
    """Acumula columnas y emite ``CREATE TABLE IF NOT EXISTS``."""

    def __init__(self, db: Database, table_name: str, *, dialect: Dialect) -> None:
        self.db = db
        self.dialect = dialect
        self.table_name = validate_identifier(table_name, kind="table")
        self._columns: list[str] = []

    # ------------------------------------------------------------------
    # Modificadores de la última columna
    # ------------------------------------------------------------------

    def _require_columns(self) -> None:
        if not self._columns:
            raise error_codes.NO_COLUMNS_DEFINED.build()

    def _append_column(self, declaration: str) -> TableBuilder:
        self._columns.append(declaration)
        return self

    def _amend_last(self, fragment: str) -> TableBuilder:
        self._require_columns()
        self._columns[-1] = f"{self._columns[-1]} {fragment}"
        return self

    def primary(self) -> TableBuilder:
        return self._amend_last("PRIMARY KEY")

    def unique(self) -> TableBuilder:
        return self._amend_last("UNIQUE")

    def nullable(self) -> TableBuilder:
        return self._amend_last("NULL")

    def not_nullable(self) -> TableBuilder:
        return self._amend_last("NOT NULL")

    def default(self, value: str | int | float | bool | None) -> TableBuilder:
        if value is None:
            return self._amend_last("DEFAULT NULL")
        if isinstance(value, bool):
            return self._amend_last(f"DEFAULT {1 if value else 0}")
        if isinstance(value, (int, float)):
            return self._amend_last(f"DEFAULT {value}")
        return self._amend_last("DEFAULT " + _escape_enum_choice(value))

    def foreign(
        self,
        foreign_name: str | None = None,
        table_name: str | None = None,
        column_name: str | None = None,
    ) -> TableBuilder:
        self._require_columns()
        if not foreign_name or not table_name or not column_name:
            raise error_codes.MISSING_REQUIRED_DATA.build(
                "foreign() requiere foreign_name, table_name y column_name."
            )
        validate_identifier(foreign_name, kind="constraint")
        last = self._columns[-1]
        current_col = last.split()[0].strip("`\"[]")
        qcol = self.dialect.quote_identifier(current_col)
        qtable = self.dialect.quote_identifier(table_name)
        qref = self.dialect.quote_identifier(column_name)
        qname = self.dialect.quote_identifier(foreign_name)
        self._columns[-1] = (
            f"{last}, CONSTRAINT {qname} FOREIGN KEY ({qcol}) REFERENCES {qtable}({qref})"
        )
        return self

    # ------------------------------------------------------------------
    # Tipos
    # ------------------------------------------------------------------

    def _col(self, column_name: str, sql_type: str) -> TableBuilder:
        validate_identifier(column_name, kind="column")
        return self._append_column(
            f"{self.dialect.quote_identifier(column_name)} {self.dialect.map_type(sql_type)}"
        )

    def increments(self, column_name: str = "id", primary_key: bool = False) -> TableBuilder:
        validate_identifier(column_name, kind="column")
        col_quoted = self.dialect.quote_identifier(column_name)
        if primary_key:
            self._append_column(self.dialect.compile_auto_increment_pk(col_quoted))
        else:
            self._append_column(f"{col_quoted} INT AUTO_INCREMENT")
        return self

    def integer(self, column_name: str, length: int | None = None) -> TableBuilder:
        sql_type = "INT" if length is None else f"INT({int(length)})"
        return self._col(column_name, sql_type)

    def big_integer(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "BIGINT")

    def small_integer(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "SMALLINT")

    def tiny_integer(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "TINYINT")

    def string(self, column_name: str, length: int = 255) -> TableBuilder:
        return self._col(column_name, f"VARCHAR({int(length)})")

    def text(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "TEXT")

    def char(self, column_name: str, length: int = 1) -> TableBuilder:
        return self._col(column_name, f"CHAR({int(length)})")

    def date(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "DATE")

    def datetime(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "DATETIME")

    def time(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "TIME")

    def timestamp(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "TIMESTAMP")

    def decimal(self, column_name: str, precision: int = 10, scale: int = 2) -> TableBuilder:
        return self._col(column_name, f"DECIMAL({int(precision)}, {int(scale)})")

    def floats(self, column_name: str, precision: int = 10, scale: int = 2) -> TableBuilder:
        return self._col(column_name, f"FLOAT({int(precision)}, {int(scale)})")

    def boolean(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "BOOLEAN")

    def binary(self, column_name: str, length: int | None = None) -> TableBuilder:
        sql_type = "BLOB" if length is None else f"BLOB({int(length)})"
        return self._col(column_name, sql_type)

    def json(self, column_name: str) -> TableBuilder:
        return self._col(column_name, "JSON")

    def enum(self, column_name: str, choices: list[str]) -> TableBuilder:
        validate_identifier(column_name, kind="column")
        if not choices:
            raise error_codes.MISSING_REQUIRED_DATA.build("enum() requiere choices.")
        choices_sql = ", ".join(_escape_enum_choice(c) for c in choices)
        return self._append_column(
            f"{self.dialect.quote_identifier(column_name)} ENUM({choices_sql})"
        )

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> TableBuilder:
        self._require_columns()
        table = self.dialect.quote_identifier(self.table_name)
        query = f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(self._columns)})"
        self.db.execute(query)
        return self

    def to_sql(self) -> str:
        """Devuelve la SQL sin ejecutarla. Útil para tests y debug."""
        self._require_columns()
        table = self.dialect.quote_identifier(self.table_name)
        return f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(self._columns)})"
