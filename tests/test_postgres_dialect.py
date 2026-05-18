"""PostgresDialect emite SQL en la sintaxis idiomática del motor."""
from __future__ import annotations

import pytest

from shiba import error_codes
from shiba.core.query_builder import QueryBuilder
from shiba.core.table_builder import TableBuilder
from shiba.dialects.postgres.dialect import PostgresDialect
from shiba.errors import MissingDataError, SchemaError


@pytest.fixture
def pg() -> PostgresDialect:
    return PostgresDialect()


def test_quotes_with_double_quotes(pg) -> None:
    assert pg.quote_identifier("users") == '"users"'
    assert pg.quote_identifier("schema.table") == '"schema"."table"'


def test_quote_rejects_injection(pg) -> None:
    with pytest.raises(SchemaError) as ei:
        pg.quote_identifier('users"; DROP TABLE x; --')
    assert ei.value.code is error_codes.INVALID_IDENTIFIER


def test_select_uses_double_quotes(fake_db, pg) -> None:
    QueryBuilder(fake_db, "users", dialect=pg).where("name", "John").get()
    sql, params, _ = fake_db.last_call
    assert sql.startswith('SELECT * FROM "users"')
    assert 'WHERE "name" = %s' in sql
    assert params == ("John",)


def test_create_table_uses_identity_pk(fake_db, pg) -> None:
    sql = (
        TableBuilder(fake_db, "users", dialect=pg)
        .increments("id", primary_key=True)
        .string("name")
        .json("settings")
        .to_sql()
    )
    assert 'CREATE TABLE IF NOT EXISTS "users"' in sql
    assert '"id" INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY' in sql
    assert '"name" VARCHAR(255)' in sql
    assert '"settings" JSONB' in sql  # JSON → JSONB


def test_datetime_maps_to_timestamp(fake_db, pg) -> None:
    sql = TableBuilder(fake_db, "t", dialect=pg).datetime("created_at").to_sql()
    assert '"created_at" TIMESTAMP' in sql
    assert "DATETIME" not in sql


def test_blob_maps_to_bytea(fake_db, pg) -> None:
    sql = TableBuilder(fake_db, "t", dialect=pg).binary("data").to_sql()
    assert '"data" BYTEA' in sql


def test_upsert_emits_on_conflict(fake_db, pg) -> None:
    QueryBuilder(fake_db, "users", dialect=pg).upsert(
        {"id": 1, "name": "X"}, on=["id"]
    )
    sql, params, _ = fake_db.last_call
    assert sql == (
        'INSERT INTO "users" ("id", "name") VALUES (%s, %s) '
        'ON CONFLICT ("id") DO UPDATE SET "id" = EXCLUDED."id", "name" = EXCLUDED."name"'
    )
    assert params == (1, "X")


def test_upsert_without_on_in_postgres_raises(fake_db, pg) -> None:
    with pytest.raises(MissingDataError) as ei:
        QueryBuilder(fake_db, "users", dialect=pg).upsert({"id": 1, "name": "X"})
    assert ei.value.code is error_codes.MISSING_REQUIRED_DATA


def test_upsert_empty_update_does_nothing(fake_db, pg) -> None:
    QueryBuilder(fake_db, "users", dialect=pg).upsert(
        {"id": 1, "name": "X"}, update=[], on=["id"]
    )
    sql, _, _ = fake_db.last_call
    assert 'ON CONFLICT ("id") DO NOTHING' in sql


def test_mysql_upsert_still_works_without_on(fake_db, dialect) -> None:
    """`on` es opcional en MySQL (lo detecta la PK)."""
    QueryBuilder(fake_db, "users", dialect=dialect).upsert({"id": 1, "name": "X"})
    sql, _, _ = fake_db.last_call
    assert "ON DUPLICATE KEY UPDATE" in sql
