"""Smoke end-to-end contra MySQL 8 real."""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.integration


def test_create_and_crud(mysql_cx) -> None:
    mysql_cx.create_table("users").increments("id", primary_key=True).string(
        "name", 64
    ).integer("age").json("settings").build()
    try:
        tbl = mysql_cx.table("users")
        tbl.insert({"name": "Alice", "age": 30, "settings": json.dumps({"theme": "dark"})})
        tbl.insert({"name": "Bob", "age": 18, "settings": json.dumps({"theme": "light"})})

        rows = mysql_cx.table("users").order_by("age").get()
        assert [r["name"] for r in rows] == ["Bob", "Alice"]

        n = mysql_cx.table("users").where("age", ">=", 18).count()
        assert n == 2

        mysql_cx.table("users").where("name", "Bob").update({"age": 19})
        bob = mysql_cx.table("users").where("name", "Bob").first()
        assert bob is not None and bob["age"] == 19

        mysql_cx.table("users").where("name", "Bob").delete()
        assert mysql_cx.table("users").count() == 1
    finally:
        mysql_cx.raw("DROP TABLE IF EXISTS users")


def test_upsert(mysql_cx) -> None:
    mysql_cx.raw("DROP TABLE IF EXISTS items")
    mysql_cx.create_table("items").integer("id").primary().string("name").build()
    try:
        mysql_cx.table("items").upsert({"id": 1, "name": "A"})
        mysql_cx.table("items").upsert({"id": 1, "name": "B"})  # actualiza
        rows = mysql_cx.table("items").get()
        assert len(rows) == 1
        assert rows[0]["name"] == "B"
    finally:
        mysql_cx.raw("DROP TABLE IF EXISTS items")


def test_transaction_rollback(mysql_cx) -> None:
    mysql_cx.raw("DROP TABLE IF EXISTS t")
    mysql_cx.create_table("t").integer("id").primary().build()
    try:
        with pytest.raises(RuntimeError), mysql_cx.transaction():
            mysql_cx.table("t").insert({"id": 1})
            raise RuntimeError("abort")
        assert mysql_cx.table("t").count() == 0

        with mysql_cx.transaction():
            mysql_cx.table("t").insert({"id": 1})
        assert mysql_cx.table("t").count() == 1
    finally:
        mysql_cx.raw("DROP TABLE IF EXISTS t")


def test_orm_end_to_end(mysql_cx) -> None:
    from shiba import Model, fields, set_default_connection

    set_default_connection(mysql_cx)

    class Customer(Model):
        __table__ = "customers"
        id: int = fields.PrimaryKey()
        name: str
        active: bool = True

    mysql_cx.raw("DROP TABLE IF EXISTS customers")
    Customer.create_table()
    try:
        Customer(name="Alice").save()
        Customer(name="Bob", active=False).save()

        rows = Customer.where("active", True).get()
        assert len(rows) == 1
        assert isinstance(rows[0], Customer)
        assert rows[0].name == "Alice"

        first = Customer.find(1)
        assert first is not None and first.name == "Alice"
        first.name = "Alice Renamed"
        first.save()
        assert Customer.find(1).name == "Alice Renamed"  # type: ignore[union-attr]
    finally:
        mysql_cx.raw("DROP TABLE IF EXISTS customers")
