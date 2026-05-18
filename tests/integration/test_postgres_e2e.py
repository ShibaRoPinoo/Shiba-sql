"""Smoke end-to-end contra Postgres 16 real."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_create_and_crud(postgres_cx) -> None:
    postgres_cx.raw("DROP TABLE IF EXISTS users")
    postgres_cx.create_table("users").increments("id", primary_key=True).string(
        "name", 64
    ).integer("age").json("settings").build()
    try:
        tbl = postgres_cx.table("users")
        tbl.insert({"name": "Alice", "age": 30, "settings": '{"theme": "dark"}'})
        tbl.insert({"name": "Bob", "age": 18, "settings": '{"theme": "light"}'})

        rows = postgres_cx.table("users").order_by("age").get()
        assert [r["name"] for r in rows] == ["Bob", "Alice"]

        n = postgres_cx.table("users").where("age", ">=", 18).count()
        assert n == 2

        postgres_cx.table("users").where("name", "Bob").update({"age": 19})
        bob = postgres_cx.table("users").where("name", "Bob").first()
        assert bob is not None and bob["age"] == 19

        postgres_cx.table("users").where("name", "Bob").delete()
        assert postgres_cx.table("users").count() == 1
    finally:
        postgres_cx.raw("DROP TABLE IF EXISTS users")


def test_upsert_with_on(postgres_cx) -> None:
    postgres_cx.raw("DROP TABLE IF EXISTS items")
    postgres_cx.create_table("items").integer("id").primary().string("name").build()
    try:
        postgres_cx.table("items").upsert({"id": 1, "name": "A"}, on=["id"])
        postgres_cx.table("items").upsert({"id": 1, "name": "B"}, on=["id"])
        rows = postgres_cx.table("items").get()
        assert len(rows) == 1
        assert rows[0]["name"] == "B"
    finally:
        postgres_cx.raw("DROP TABLE IF EXISTS items")


def test_identity_pk_generated(postgres_cx) -> None:
    postgres_cx.raw("DROP TABLE IF EXISTS pk_test")
    postgres_cx.create_table("pk_test").increments("id", primary_key=True).string(
        "label"
    ).build()
    try:
        postgres_cx.table("pk_test").insert({"label": "a"})
        postgres_cx.table("pk_test").insert({"label": "b"})
        ids = [r["id"] for r in postgres_cx.table("pk_test").order_by("id").get()]
        assert ids == [1, 2]
    finally:
        postgres_cx.raw("DROP TABLE IF EXISTS pk_test")
