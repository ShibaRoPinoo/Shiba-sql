"""QueryBuilder genera SQL parametrizado correcto."""
from __future__ import annotations

import pytest

from shiba import error_codes
from shiba.core.query_builder import QueryBuilder
from shiba.errors import MissingDataError, SchemaError


def test_select_quotes_columns(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).select("id", "name").get()
    sql, params, many = fake_db.last_call
    assert sql.startswith("SELECT `id`, `name` FROM `users`")
    assert params is None
    assert many is False


def test_where_parametrizes_value(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).where("name", "John").get()
    sql, params, _ = fake_db.last_call
    assert "WHERE `name` = %s" in sql
    assert params == ("John",)


def test_where_rejects_injection_in_value_via_params(fake_db, dialect) -> None:
    # El valor con inyección llega como parámetro, no concatenado.
    payload = "x' OR '1'='1"
    QueryBuilder(fake_db, "users", dialect=dialect).where("name", payload).get()
    sql, params, _ = fake_db.last_call
    assert payload not in sql
    assert params == (payload,)


def test_where_rejects_injection_in_column(fake_db, dialect) -> None:
    with pytest.raises(SchemaError) as ei:
        QueryBuilder(fake_db, "users", dialect=dialect).where("name; DROP", "x").get()
    assert ei.value.code is error_codes.INVALID_IDENTIFIER


def test_where_rejects_bad_operator(fake_db, dialect) -> None:
    with pytest.raises(SchemaError) as ei:
        QueryBuilder(fake_db, "users", dialect=dialect).where("name", "OR 1=1", "x").get()
    assert ei.value.code is error_codes.INVALID_OPERATOR


def test_where_in_expands_placeholders(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).where("id", "IN", [1, 2, 3]).get()
    sql, params, _ = fake_db.last_call
    assert "`id` IN (%s, %s, %s)" in sql
    assert params == (1, 2, 3)


def test_where_array_does_not_crash_on_three_element_condition(fake_db, dialect) -> None:
    # Regresión: en v1.x _whereArray accedía a `value` sin definir cuando
    # la condición tenía 3 elementos.
    QueryBuilder(fake_db, "users", dialect=dialect).where(
        [["age", ">", 18], ["name", "Alice"]]
    ).get()
    sql, params, _ = fake_db.last_call
    assert "`age` > %s" in sql
    assert "`name` = %s" in sql
    assert params == (18, "Alice")


def test_join_quotes_identifiers(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).left_join(
        "orders", "users.id", "=", "orders.user_id"
    ).get()
    sql, _, _ = fake_db.last_call
    assert "LEFT JOIN `orders` ON `users`.`id` = `orders`.`user_id`" in sql


def test_order_by_and_limit(fake_db, dialect) -> None:
    (
        QueryBuilder(fake_db, "users", dialect=dialect)
        .order_by("name", "DESC")
        .limit(10)
        .offset(5)
        .get()
    )
    sql, _, _ = fake_db.last_call
    assert "ORDER BY `name` DESC" in sql
    assert "LIMIT 10" in sql
    assert "OFFSET 5" in sql


def test_insert_single(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).insert({"name": "John", "age": 30})
    sql, params, many = fake_db.last_call
    assert sql == "INSERT INTO `users` (`name`, `age`) VALUES (%s, %s)"
    assert params == ("John", 30)
    assert many is False


def test_insert_many(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).insert(
        [{"name": "A", "age": 1}, {"name": "B", "age": 2}]
    )
    sql, params, many = fake_db.last_call
    assert sql == "INSERT INTO `users` (`name`, `age`) VALUES (%s, %s)"
    assert params == [("A", 1), ("B", 2)]
    assert many is True


def test_insert_many_rejects_mismatched_keys(fake_db, dialect) -> None:
    with pytest.raises(MissingDataError) as ei:
        QueryBuilder(fake_db, "users", dialect=dialect).insert(
            [{"name": "A", "age": 1}, {"age": 2, "name": "B"}]
        )
    assert ei.value.code is error_codes.INVALID_DATA_FORMAT


def test_update(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).where("id", 1).update({"name": "X"})
    sql, params, _ = fake_db.last_call
    assert sql == "UPDATE `users` SET `name` = %s WHERE `id` = %s"
    assert params == ("X", 1)


def test_delete_requires_where(fake_db, dialect) -> None:
    with pytest.raises(MissingDataError) as ei:
        QueryBuilder(fake_db, "users", dialect=dialect).delete()
    assert ei.value.code is error_codes.MISSING_REQUIRED_DATA


def test_delete_with_where(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).where("id", 1).delete()
    sql, params, _ = fake_db.last_call
    assert sql == "DELETE FROM `users` WHERE `id` = %s"
    assert params == (1,)


def test_count(fake_db, dialect) -> None:
    fake_db.result = [{"v": 42}]
    n = QueryBuilder(fake_db, "users", dialect=dialect).where("active", True).count()
    assert n == 42
    sql, _, _ = fake_db.last_call
    assert sql.startswith("SELECT COUNT(*) AS v FROM `users`")
