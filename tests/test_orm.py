"""Cobertura del ORM (fields + Model + ModelQuery)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from shiba import Model, error_codes, fields, set_default_connection
from shiba.core.query_builder import QueryBuilder
from shiba.core.table_builder import TableBuilder
from shiba.dialects.mysql import MySQLDialect
from shiba.errors import MissingDataError, ShibaError

# ---------------------------------------------------------------------------
# Fake connection que reusa el FakeDatabase de conftest
# ---------------------------------------------------------------------------


class FakeShibaConnection:
    def __init__(self, fake_db: Any) -> None:
        self.db = fake_db
        self.dialect = MySQLDialect()

    def table(self, name: str) -> QueryBuilder:
        return QueryBuilder(self.db, name, dialect=self.dialect)

    def create_table(self, name: str) -> TableBuilder:
        return TableBuilder(self.db, name, dialect=self.dialect)

    def raw(self, query: str, params: Any = None, *, many: bool = False):
        return self.db.execute(query, params, many=many)


@pytest.fixture
def cx(fake_db) -> FakeShibaConnection:
    conn = FakeShibaConnection(fake_db)
    set_default_connection(conn)  # type: ignore[arg-type]
    return conn


# ---------------------------------------------------------------------------
# Field inference
# ---------------------------------------------------------------------------


def test_infer_types_from_annotations() -> None:
    class T(Model):
        __table__ = "t"
        id: int = fields.PrimaryKey()
        name: str
        age: int | None = None
        active: bool = True
        score: float = 0.0
        amount: Decimal | None = None
        settings: dict = fields.Json(default_factory=dict)
        notes: str | None = None
        created_at: datetime = fields.DateTime(default_now=True)

    f = T._fields
    assert f["id"].primary_key and f["id"].auto_increment
    assert f["name"].sql_type == "VARCHAR(255)" and not f["name"].nullable
    assert f["age"].sql_type == "INT" and f["age"].nullable
    assert f["active"].sql_type == "BOOLEAN" and f["active"].default is True
    assert f["score"].sql_type == "FLOAT"
    assert f["amount"].sql_type == "DECIMAL" and f["amount"].nullable
    assert f["settings"].json and f["settings"].sql_type == "JSON"
    assert f["notes"].nullable
    assert f["created_at"].default_factory is not None


def test_unknown_kwarg_rejected(cx) -> None:
    class T(Model):
        __table__ = "t"
        id: int = fields.PrimaryKey()
        name: str

    with pytest.raises(ShibaError) as ei:
        T(name="x", oops=1)
    assert ei.value.code is error_codes.INVALID_DATA_FORMAT


def test_pk_required(cx) -> None:
    class NoPk(Model):
        __table__ = "nopk"
        name: str

    with pytest.raises(MissingDataError) as ei:
        NoPk(name="x").save()
    assert ei.value.code is error_codes.MISSING_REQUIRED_DATA


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


def test_save_insert(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str
        age: int | None = None

    # Para que save() interprete LAST_INSERT_ID le damos un retorno.
    seq = iter([[], [{"v": 42}]])

    def execute(query, params=None, **kwargs):
        fake_db.calls.append((query, params, kwargs.get("many", False)))
        return next(seq)

    fake_db.execute = execute  # type: ignore[method-assign]

    u = User(name="John", age=30)
    u.save()
    assert u.id == 42
    insert_sql, params, _ = fake_db.calls[0]
    assert insert_sql.startswith("INSERT INTO `users` (`name`, `age`)")
    assert params == ("John", 30)


def test_save_update_when_pk_present(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str

    u = User(id=5, name="John")
    u.save()
    sql, params, _ = fake_db.last_call
    assert sql == "UPDATE `users` SET `id` = %s, `name` = %s WHERE `id` = %s"
    assert params == (5, "John", 5)


def test_delete(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str

    User(id=7, name="X").delete()
    sql, params, _ = fake_db.last_call
    assert sql == "DELETE FROM `users` WHERE `id` = %s"
    assert params == (7,)


def test_delete_without_pk_raises(cx) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str

    with pytest.raises(MissingDataError) as ei:
        User(name="X").delete()
    assert ei.value.code is error_codes.MISSING_REQUIRED_DATA


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


def test_find_returns_model_instance(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str

    fake_db.result = [{"id": 3, "name": "Alice"}]
    u = User.find(3)
    assert isinstance(u, User)
    assert u.id == 3
    assert u.name == "Alice"


def test_find_returns_none_when_missing(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str

    fake_db.result = []
    assert User.find(99) is None


def test_where_returns_modelquery(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str
        age: int

    fake_db.result = [
        {"id": 1, "name": "A", "age": 20},
        {"id": 2, "name": "B", "age": 30},
    ]
    rows = User.where("age", ">", 10).order_by("age").get()
    assert all(isinstance(r, User) for r in rows)
    assert [r.name for r in rows] == ["A", "B"]
    sql, params, _ = fake_db.last_call
    assert "WHERE `age` > %s" in sql
    assert "ORDER BY `age` ASC" in sql
    assert params == (10,)


def test_json_field_roundtrips(cx, fake_db) -> None:
    class Doc(Model):
        __table__ = "docs"
        id: int = fields.PrimaryKey()
        payload: dict = fields.Json(default_factory=dict)

    fake_db.result = [{"id": 1, "payload": '{"a": 1}'}]
    d = Doc.find(1)
    assert d is not None
    assert d.payload == {"a": 1}

    # Y al guardar, payload se serializa.
    fake_db.result = []
    Doc(payload={"x": "y"}).save()
    insert_calls = [c for c in fake_db.calls if c[0].startswith("INSERT INTO `docs`")]
    assert insert_calls, "esperaba al menos un INSERT"
    _, params, _ = insert_calls[-1]
    assert params == ('{"x": "y"}',)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_create_table_emits_ddl(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str = fields.String(max_length=50)
        email: str = fields.String(unique=True)
        age: int | None = None
        settings: dict = fields.Json(default_factory=dict)

    User.create_table()
    sql, _, _ = fake_db.last_call
    assert "CREATE TABLE IF NOT EXISTS `users`" in sql
    assert "`id` INT AUTO_INCREMENT PRIMARY KEY" in sql
    assert "`name` VARCHAR(50) NOT NULL" in sql
    assert "`email` VARCHAR(255) UNIQUE NOT NULL" in sql
    assert "`age` INT NULL" in sql
    assert "`settings` JSON NOT NULL" in sql


def test_truncate_table(cx, fake_db) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str

    User.truncate_table()
    sql, _, _ = fake_db.last_call
    assert sql == "TRUNCATE TABLE `users`"


def test_default_table_name_from_class(cx) -> None:
    class Customer(Model):
        id: int = fields.PrimaryKey()
        name: str

    assert Customer._table == "customer"


def test_to_dict_and_from_row_roundtrip(cx) -> None:
    class User(Model):
        __table__ = "users"
        id: int = fields.PrimaryKey()
        name: str

    u = User.from_row({"id": 1, "name": "X"})
    assert u.to_dict() == {"id": 1, "name": "X"}


def test_no_connection_raises(monkeypatch) -> None:
    from shiba.orm import model as model_mod

    monkeypatch.setattr(model_mod, "_default_connection", None)

    class T(Model):
        __table__ = "t"
        id: int = fields.PrimaryKey()
        name: str

    T.__db__ = None
    with pytest.raises(ShibaError) as ei:
        T.find(1)
    assert ei.value.code is error_codes.CONNECTION_NOT_OPEN
