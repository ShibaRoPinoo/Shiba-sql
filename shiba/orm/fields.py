"""Field descriptors para modelos Shiba.

Los modelos del ORM combinan anotaciones Python (que dan el tipo) con
instancias de :class:`Field` (que dan metadata extra: unique, default,
auto-increment, etc.). Cuando un atributo sólo tiene anotación, el
:class:`Field` se infiere automáticamente con defaults razonables.
"""
from __future__ import annotations

import json
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Union, get_args, get_origin

from shiba import error_codes

_UNSET: Any = object()
"""Sentinel para distinguir 'no se pasó valor' de 'None explícito'."""


@dataclass
class Field:
    """Descriptor de columna SQL.

    Casi nunca se instancia directamente — se usan las subclases
    semánticas (:class:`String`, :class:`Integer`, etc.) y la inferencia
    desde anotaciones.
    """

    sql_type: str = "VARCHAR(255)"
    nullable: bool = False
    primary_key: bool = False
    unique: bool = False
    auto_increment: bool = False
    default: Any = _UNSET
    default_factory: Callable[[], Any] | None = None
    column_name: str | None = None
    foreign_key: tuple[str, str] | None = None
    json: bool = False
    enum_choices: tuple[str, ...] | None = None
    indexed: bool = False

    # --- Conversión Python <-> DB --------------------------------------

    def to_python(self, raw: Any) -> Any:
        """Decodifica el valor que llega desde la fila SQL."""
        if raw is None:
            return None
        if self.json and isinstance(raw, (str, bytes)):
            return json.loads(raw)
        return raw

    def to_db(self, value: Any) -> Any:
        """Codifica el valor antes de enviarlo a la base de datos."""
        if value is None:
            return None
        if self.json and not isinstance(value, (str, bytes)):
            return json.dumps(value, default=str)
        return value

    # --- Defaults -------------------------------------------------------

    def has_default(self) -> bool:
        return self.default is not _UNSET or self.default_factory is not None

    def get_default(self) -> Any:
        if self.default_factory is not None:
            return self.default_factory()
        if self.default is _UNSET:
            return None
        return self.default

    # --- DDL ------------------------------------------------------------

    def apply_to_table_builder(self, tb: Any, column_name: str) -> None:
        """Replica este campo en el ``TableBuilder``."""
        col = self.column_name or column_name
        # Tipo
        if self.primary_key and self.auto_increment and self.sql_type == "INT":
            tb.increments(col, primary_key=True)
        elif self.enum_choices is not None:
            tb.enum(col, list(self.enum_choices))
        else:
            # Reusar map de tipos via raw type string.
            type_lower = self.sql_type.lower()
            if type_lower.startswith("varchar"):
                length = int(self.sql_type[8:-1]) if "(" in self.sql_type else 255
                tb.string(col, length)
            elif type_lower == "text":
                tb.text(col)
            elif type_lower.startswith("int"):
                tb.integer(col)
            elif type_lower == "bigint":
                tb.big_integer(col)
            elif type_lower == "smallint":
                tb.small_integer(col)
            elif type_lower == "tinyint":
                tb.tiny_integer(col)
            elif type_lower == "boolean":
                tb.boolean(col)
            elif type_lower == "json":
                tb.json(col)
            elif type_lower == "datetime":
                tb.datetime(col)
            elif type_lower == "date":
                tb.date(col)
            elif type_lower == "time":
                tb.time(col)
            elif type_lower == "timestamp":
                tb.timestamp(col)
            elif type_lower.startswith("decimal"):
                tb.decimal(col)
            elif type_lower.startswith("float") or type_lower == "double":
                tb.floats(col)
            elif type_lower == "blob":
                tb.binary(col)
            else:
                error_codes.UNSUPPORTED_TYPE.raise_(
                    f"tipo {self.sql_type!r} no soportado por apply_to_table_builder."
                )
        # Constraints adicionales — añadidas al último column declared.
        if self.primary_key and not self.auto_increment:
            tb.primary()
        if self.unique:
            tb.unique()
        if self.nullable:
            tb.nullable()
        elif not self.primary_key:
            tb.not_nullable()
        if self.default is not _UNSET and self.default_factory is None:
            tb.default(self.default)
        if self.foreign_key is not None:
            ftable, fcolumn = self.foreign_key
            tb.foreign(f"fk_{col}_{ftable}", ftable, fcolumn)


# ---------------------------------------------------------------------------
# Subclases semánticas
# ---------------------------------------------------------------------------


@dataclass
class PrimaryKey(Field):
    sql_type: str = "INT"
    primary_key: bool = True
    auto_increment: bool = True


@dataclass
class String(Field):
    max_length: int = 255

    def __post_init__(self) -> None:
        self.sql_type = f"VARCHAR({self.max_length})"


@dataclass
class Text(Field):
    sql_type: str = "TEXT"


@dataclass
class Integer(Field):
    sql_type: str = "INT"


@dataclass
class BigInteger(Field):
    sql_type: str = "BIGINT"


@dataclass
class Boolean(Field):
    sql_type: str = "BOOLEAN"

    def to_python(self, raw: Any) -> Any:
        if raw is None:
            return None
        return bool(raw)


@dataclass
class FloatField(Field):
    sql_type: str = "FLOAT"


@dataclass
class DecimalField(Field):
    sql_type: str = "DECIMAL"

    def to_python(self, raw: Any) -> Any:
        if raw is None:
            return None
        return Decimal(str(raw))


@dataclass
class DateTime(Field):
    sql_type: str = "DATETIME"
    default_now: bool = False

    def __post_init__(self) -> None:
        if self.default_now and self.default_factory is None:
            self.default_factory = datetime.now

    def to_python(self, raw: Any) -> Any:
        if raw is None or isinstance(raw, datetime):
            return raw
        return datetime.fromisoformat(str(raw))


@dataclass
class DateField(Field):
    sql_type: str = "DATE"

    def to_python(self, raw: Any) -> Any:
        if raw is None or isinstance(raw, date):
            return raw
        return date.fromisoformat(str(raw))


@dataclass
class Json(Field):
    sql_type: str = "JSON"
    json: bool = True


@dataclass
class Enum(Field):
    choices: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.choices:
            error_codes.MISSING_REQUIRED_DATA.raise_(
                "Enum requiere choices."
            )
        self.sql_type = "ENUM"
        self.enum_choices = self.choices


@dataclass
class ForeignKey(Field):
    """``ForeignKey(to='users', column='id')``."""

    to: str = ""
    column: str = "id"
    sql_type: str = "INT"

    def __post_init__(self) -> None:
        if not self.to:
            error_codes.MISSING_REQUIRED_DATA.raise_(
                "ForeignKey requiere `to` (tabla destino)."
            )
        self.foreign_key = (self.to, self.column)


# ---------------------------------------------------------------------------
# Inferencia desde anotaciones
# ---------------------------------------------------------------------------


def _is_optional(hint: Any) -> tuple[bool, Any]:
    """Devuelve ``(nullable, inner_type)`` para ``X | None``."""
    origin = get_origin(hint)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(hint) if a is not type(None)]
        if len(get_args(hint)) > len(args):
            return True, args[0] if len(args) == 1 else hint
    return False, hint


def infer_field(hint: Any, default: Any = _UNSET) -> Field:
    """Construye un :class:`Field` a partir de la anotación del atributo."""
    nullable, inner = _is_optional(hint)
    has_default = default is not _UNSET
    f: Field

    if inner is str:
        f = String()
    elif inner is int:
        f = Integer()
    elif inner is bool:
        f = Boolean()
    elif inner is float:
        f = FloatField()
    elif inner is Decimal:
        f = DecimalField()
    elif inner is datetime:
        f = DateTime()
    elif inner is date:
        f = DateField()
    elif inner is bytes:
        f = Field(sql_type="BLOB")
    elif inner is dict or get_origin(inner) is dict or inner is list or get_origin(inner) is list:
        f = Json()
    else:
        f = Field()

    f.nullable = nullable or (has_default and default is None)
    if has_default:
        f.default = default
    return f
