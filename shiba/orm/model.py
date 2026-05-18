"""Modelos POO con metaclass que lee anotaciones."""
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from shiba import error_codes
from shiba.orm.fields import _UNSET, Field, infer_field

if TYPE_CHECKING:
    from shiba import ShibaConnection
    from shiba.core.query_builder import QueryBuilder


T = TypeVar("T", bound="Model")


_default_connection: ShibaConnection | None = None


def set_default_connection(connection: ShibaConnection) -> None:
    """Registra la conexión global usada por modelos sin ``__db__``."""
    global _default_connection
    _default_connection = connection


def get_default_connection() -> ShibaConnection | None:
    return _default_connection


class ModelMeta(type):
    """Metaclass que extrae ``_fields`` desde las anotaciones de la clase."""

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        ns: dict[str, Any],
    ) -> ModelMeta:
        cls = super().__new__(mcs, name, bases, ns)

        # No procesamos la propia clase base ``Model``.
        if ns.get("__shiba_model_root__", False):
            return cls

        # Recolectamos anotaciones por clase del MRO, evaluando strings
        # con eval_str. Esto evita fallar si una clase ancestra tiene
        # forward refs no resolvibles (p. ej. ``ShibaConnection``).
        annotations: dict[str, Any] = {}
        for klass in reversed(cls.__mro__):
            if klass is object:
                continue
            try:
                hints = inspect.get_annotations(klass, eval_str=True)
            except (NameError, AttributeError):
                hints = inspect.get_annotations(klass, eval_str=False)
            annotations.update(hints)

        fields: dict[str, Field] = {}
        for attr, hint in annotations.items():
            if attr.startswith("_") or attr in {"ClassVar"}:
                continue
            value = ns.get(attr, _UNSET)
            fld = value if isinstance(value, Field) else infer_field(hint, default=value)
            fields[attr] = fld

            # Quitamos el Field del namespace para que la lookup pase por
            # la instancia y no devuelva el descriptor.
            if attr in cls.__dict__ and isinstance(cls.__dict__[attr], Field):
                delattr(cls, attr)

        cls._fields = fields  # type: ignore[attr-defined]
        cls._table = ns.get("__table__", name.lower())  # type: ignore[attr-defined]
        return cls


class Model(metaclass=ModelMeta):
    """Base de cualquier modelo. Se levanta como objeto Python plano."""

    __shiba_model_root__: ClassVar[bool] = True
    _fields: ClassVar[dict[str, Field]] = {}
    _table: ClassVar[str] = ""
    __db__: ClassVar[Any] = None  # ShibaConnection | None — tipado en docstring

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def __init__(self, **kwargs: Any) -> None:
        unknown = set(kwargs) - set(self._fields)
        if unknown:
            error_codes.INVALID_DATA_FORMAT.raise_(
                f"{type(self).__name__}: claves desconocidas {sorted(unknown)}",
                details={"unknown": sorted(unknown)},
            )
        for attr, fld in self._fields.items():
            if attr in kwargs:
                setattr(self, attr, kwargs[attr])
            elif fld.has_default():
                setattr(self, attr, fld.get_default())
            else:
                setattr(self, attr, None)

    def __repr__(self) -> str:
        pairs = ", ".join(f"{k}={getattr(self, k, None)!r}" for k in self._fields)
        return f"{type(self).__name__}({pairs})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Model) or type(self) is not type(other):
            return NotImplemented
        return bool(self.to_dict() == other.to_dict())

    def __hash__(self) -> int:  # pragma: no cover - identidad por pk
        pk_attr = self._pk_attr()
        return hash((type(self).__name__, getattr(self, pk_attr, None)))

    # ------------------------------------------------------------------
    # Introspección
    # ------------------------------------------------------------------

    @classmethod
    def _pk_attr(cls) -> str:
        for attr, fld in cls._fields.items():
            if fld.primary_key:
                return attr
        error_codes.MISSING_REQUIRED_DATA.raise_(
            f"{cls.__name__}: ningún campo marcado como primary_key."
        )

    def to_dict(self) -> dict[str, Any]:
        return {attr: getattr(self, attr, None) for attr in self._fields}

    def to_db_dict(self, *, exclude_pk_if_none: bool = True) -> dict[str, Any]:
        """Devuelve el dict listo para INSERT/UPDATE."""
        pk_attr = self._pk_attr()
        out: dict[str, Any] = {}
        for attr, fld in self._fields.items():
            value = getattr(self, attr, None)
            if (
                attr == pk_attr
                and exclude_pk_if_none
                and (value is None or value == _UNSET)
            ):
                continue
            col = fld.column_name or attr
            out[col] = fld.to_db(value)
        return out

    @classmethod
    def from_row(cls: type[T], row: dict[str, Any]) -> T:
        """Hidrata una instancia desde una fila ``dict``."""
        instance = cls.__new__(cls)
        for attr, fld in cls._fields.items():
            col = fld.column_name or attr
            raw = row.get(col)
            setattr(instance, attr, fld.to_python(raw))
        return instance

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    @classmethod
    def _connection(cls) -> ShibaConnection:
        conn: ShibaConnection | None = cls.__db__ or _default_connection
        if conn is None:
            error_codes.CONNECTION_NOT_OPEN.raise_(
                f"{cls.__name__} no tiene conexión. Llama a "
                "shiba.set_default_connection(cx) o asigna `__db__`."
            )
        return conn

    # ------------------------------------------------------------------
    # Query API a nivel de clase
    # ------------------------------------------------------------------

    @classmethod
    def query(cls: type[T]) -> ModelQuery[T]:
        return ModelQuery(cls)

    @classmethod
    def all(cls: type[T]) -> list[T]:
        return cls.query().get()

    @classmethod
    def find(cls: type[T], pk_value: Any) -> T | None:
        row = cls._connection().table(cls._table).find(pk_value, pk=cls._pk_attr())
        return cls.from_row(row) if row else None

    @classmethod
    def where(cls: type[T], *args: Any) -> ModelQuery[T]:
        return cls.query().where(*args)

    @classmethod
    def first(cls: type[T]) -> T | None:
        return cls.query().first()

    @classmethod
    def count(cls) -> int:
        return cls._connection().table(cls._table).count()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @classmethod
    def create_table(cls) -> None:
        tb = cls._connection().create_table(cls._table)
        for attr, fld in cls._fields.items():
            fld.apply_to_table_builder(tb, attr)
        tb.build()

    @classmethod
    def drop_table(cls) -> None:
        cx = cls._connection()
        cx.raw(f"DROP TABLE IF EXISTS {cx.dialect.quote_identifier(cls._table)}")

    @classmethod
    def truncate_table(cls) -> None:
        cls._connection().table(cls._table).truncate()

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def save(self: T) -> T:
        pk_attr = self._pk_attr()
        pk_val = getattr(self, pk_attr, None)
        cx = self._connection()
        data = self.to_db_dict(exclude_pk_if_none=True)
        if pk_val is None:
            cx.table(self._table).insert(data)
            new_id = cx.raw("SELECT LAST_INSERT_ID() AS v")
            if new_id and new_id[0].get("v"):
                setattr(self, pk_attr, new_id[0]["v"])
        else:
            cx.table(self._table).where(pk_attr, pk_val).update(data)
        return self

    def delete(self) -> None:
        pk_attr = self._pk_attr()
        pk_val = getattr(self, pk_attr, None)
        if pk_val is None:
            error_codes.MISSING_REQUIRED_DATA.raise_(
                f"delete(): {type(self).__name__} sin PK."
            )
        self._connection().table(self._table).where(pk_attr, pk_val).delete()


# ---------------------------------------------------------------------------
# Manager hidratante
# ---------------------------------------------------------------------------


class ModelQuery(Generic[T]):
    """Wrapper de :class:`QueryBuilder` que devuelve modelos en vez de dicts."""

    def __init__(self, model_cls: type[T]) -> None:
        self.model_cls = model_cls
        cx = model_cls._connection()
        self._qb: QueryBuilder = cx.table(model_cls._table)

    # Delegación al builder con retorno fluido.
    def where(self, *args: Any) -> ModelQuery[T]:
        self._qb.where(*args)
        return self

    def or_where(self, *args: Any) -> ModelQuery[T]:
        self._qb.or_where(*args)
        return self

    def where_in(self, column: str, values: list[Any]) -> ModelQuery[T]:
        self._qb.where_in(column, values)
        return self

    def where_null(self, column: str) -> ModelQuery[T]:
        self._qb.where_null(column)
        return self

    def where_not_null(self, column: str) -> ModelQuery[T]:
        self._qb.where_not_null(column)
        return self

    def order_by(self, column: str, direction: str = "ASC") -> ModelQuery[T]:
        self._qb.order_by(column, direction)
        return self

    def limit(self, n: int) -> ModelQuery[T]:
        self._qb.limit(n)
        return self

    def offset(self, n: int) -> ModelQuery[T]:
        self._qb.offset(n)
        return self

    # Ejecución hidratada.
    def get(self) -> list[T]:
        rows = self._qb.get()
        return [self.model_cls.from_row(r) for r in rows]

    def first(self) -> T | None:
        row = self._qb.first()
        return self.model_cls.from_row(row) if row else None

    def count(self) -> int:
        return self._qb.count()

    def exists(self) -> bool:
        return self._qb.exists()

    def paginate(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        result = self._qb.paginate(page, per_page)
        result["data"] = [self.model_cls.from_row(r) for r in result["data"]]
        return result
