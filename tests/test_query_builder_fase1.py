"""Cobertura de features añadidas en Fase 1.

WHERE: or_where, where_in/null/between/like, where_group, where_json.
GROUP BY / HAVING. paginate / chunk / iterate. find / exists / pluck.
sum/avg/min/max. upsert. truncate. raw().
"""
from __future__ import annotations

import pytest

from shiba import error_codes
from shiba.core.query_builder import QueryBuilder
from shiba.errors import QueryError, SchemaError

# ---------------------------------------------------------------------------
# WHERE variants
# ---------------------------------------------------------------------------

def test_or_where(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "users", dialect=dialect).where("a", 1).or_where("b", 2).get()
    sql, params, _ = fake_db.last_call
    assert "WHERE `a` = %s OR `b` = %s" in sql
    assert params == (1, 2)


def test_where_in_alias(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).where_in("id", [1, 2]).get()
    sql, params, _ = fake_db.last_call
    assert "WHERE `id` IN (%s, %s)" in sql
    assert params == (1, 2)


def test_where_null(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).where_null("deleted_at").get()
    sql, _, _ = fake_db.last_call
    assert "WHERE `deleted_at` IS NULL" in sql


def test_where_not_null(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).where_not_null("email").get()
    sql, _, _ = fake_db.last_call
    assert "WHERE `email` IS NOT NULL" in sql


def test_where_between(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).where_between("age", 18, 65).get()
    sql, params, _ = fake_db.last_call
    assert "WHERE `age` BETWEEN %s AND %s" in sql
    assert params == (18, 65)


def test_where_like(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).where_like("name", "John%").get()
    sql, params, _ = fake_db.last_call
    assert "WHERE `name` LIKE %s" in sql
    assert params == ("John%",)


def test_where_group_mixes_and_or(fake_db, dialect) -> None:
    (
        QueryBuilder(fake_db, "u", dialect=dialect)
        .where("active", True)
        .where_group(lambda g: g.where("role", "admin").or_where("role", "owner"))
        .get()
    )
    sql, params, _ = fake_db.last_call
    assert "WHERE `active` = %s AND (`role` = %s OR `role` = %s)" in sql
    assert params == (True, "admin", "owner")


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def test_where_json_extracts_path(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).where_json("settings", "$.theme", "dark").get()
    sql, params, _ = fake_db.last_call
    assert "JSON_UNQUOTE(JSON_EXTRACT(`settings`, '$.theme')) = %s" in sql
    assert params == ("dark",)


def test_where_json_rejects_unsafe_path(fake_db, dialect) -> None:
    with pytest.raises(QueryError) as ei:
        QueryBuilder(fake_db, "u", dialect=dialect).where_json(
            "settings", "$.theme'; DROP TABLE x; --", "dark"
        )
    assert ei.value.code is error_codes.INVALID_QUERY_PARAMS


# ---------------------------------------------------------------------------
# GROUP BY / HAVING
# ---------------------------------------------------------------------------

def test_group_by_and_having(fake_db, dialect) -> None:
    fake_db.result = [{"v": 0}]
    (
        QueryBuilder(fake_db, "orders", dialect=dialect)
        .select("user_id")
        .group_by("user_id")
        .having("total", ">", 100)
        .get()
    )
    sql, params, _ = fake_db.last_call
    assert "GROUP BY `user_id`" in sql
    assert "HAVING `total` > %s" in sql
    assert params == (100,)


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,fn",
    [("sum", "SUM"), ("avg", "AVG"), ("min", "MIN"), ("max", "MAX")],
)
def test_aggregates(fake_db, dialect, method: str, fn: str) -> None:
    fake_db.result = [{"v": 7}]
    qb = QueryBuilder(fake_db, "u", dialect=dialect)
    result = getattr(qb, method)("age")
    assert result == 7
    sql, _, _ = fake_db.last_call
    assert f"SELECT {fn}(`age`) AS v FROM `users`".replace("`users`", "`u`") in sql


# ---------------------------------------------------------------------------
# Convenience reads
# ---------------------------------------------------------------------------

def test_find_by_pk(fake_db, dialect) -> None:
    fake_db.result = [{"id": 5, "name": "X"}]
    row = QueryBuilder(fake_db, "u", dialect=dialect).find(5)
    assert row == {"id": 5, "name": "X"}
    sql, params, _ = fake_db.last_call
    assert "WHERE `id` = %s" in sql
    assert "LIMIT 1" in sql
    assert params == (5,)


def test_exists_true_false(fake_db, dialect) -> None:
    fake_db.result = [{"v": 3}]
    assert QueryBuilder(fake_db, "u", dialect=dialect).exists() is True
    fake_db.result = [{"v": 0}]
    assert QueryBuilder(fake_db, "u", dialect=dialect).exists() is False


def test_pluck(fake_db, dialect) -> None:
    fake_db.result = [{"name": "A"}, {"name": "B"}]
    names = QueryBuilder(fake_db, "u", dialect=dialect).pluck("name")
    assert names == ["A", "B"]
    sql, _, _ = fake_db.last_call
    assert sql.startswith("SELECT `name` FROM `u`")


# ---------------------------------------------------------------------------
# Paginate
# ---------------------------------------------------------------------------

def test_paginate(fake_db, dialect) -> None:
    # Primer execute = COUNT; segundo = data.
    results = iter([[{"v": 53}], [{"id": i} for i in range(1, 26)]])

    def execute(query, params=None, **kwargs):
        fake_db.calls.append((query, params, kwargs.get("many", False)))
        return next(results)

    fake_db.execute = execute  # type: ignore[method-assign]

    page = QueryBuilder(fake_db, "u", dialect=dialect).paginate(page=2, per_page=25)
    assert page["page"] == 2
    assert page["per_page"] == 25
    assert page["total"] == 53
    assert page["last_page"] == 3
    assert len(page["data"]) == 25
    # La segunda llamada debe tener LIMIT 25 OFFSET 25.
    data_sql, _, _ = fake_db.calls[-1]
    assert "LIMIT 25" in data_sql
    assert "OFFSET 25" in data_sql


def test_paginate_rejects_zero(fake_db, dialect) -> None:
    with pytest.raises(QueryError) as ei:
        QueryBuilder(fake_db, "u", dialect=dialect).paginate(page=0, per_page=10)
    assert ei.value.code is error_codes.INVALID_QUERY_PARAMS


# ---------------------------------------------------------------------------
# Chunk / iterate
# ---------------------------------------------------------------------------

def test_chunk_iterates_until_empty(fake_db, dialect) -> None:
    pages = iter(
        [
            [{"id": 1}, {"id": 2}],
            [{"id": 3}, {"id": 4}],
            [{"id": 5}],
            [],  # nunca debería pedirse pero por seguridad
        ]
    )

    def execute(query, params=None, **kwargs):
        fake_db.calls.append((query, params, kwargs.get("many", False)))
        return next(pages)

    fake_db.execute = execute  # type: ignore[method-assign]

    collected: list[dict[str, int]] = []
    QueryBuilder(fake_db, "u", dialect=dialect).chunk(2, collected.extend)
    assert [r["id"] for r in collected] == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# UPSERT / TRUNCATE / RAW
# ---------------------------------------------------------------------------

def test_upsert_emits_on_duplicate_key(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).upsert({"id": 1, "name": "X"})
    sql, params, _ = fake_db.last_call
    assert sql == (
        "INSERT INTO `u` (`id`, `name`) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE `id` = VALUES(`id`), `name` = VALUES(`name`)"
    )
    assert params == (1, "X")


def test_upsert_with_explicit_update_columns(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).upsert(
        {"id": 1, "name": "X", "age": 30}, update=["name", "age"]
    )
    sql, _, _ = fake_db.last_call
    assert "ON DUPLICATE KEY UPDATE `name` = VALUES(`name`), `age` = VALUES(`age`)" in sql


def test_truncate(fake_db, dialect) -> None:
    QueryBuilder(fake_db, "u", dialect=dialect).truncate()
    sql, _, _ = fake_db.last_call
    assert sql == "TRUNCATE TABLE `u`"


def test_invalid_column_in_pluck(fake_db, dialect) -> None:
    with pytest.raises(SchemaError):
        QueryBuilder(fake_db, "u", dialect=dialect).pluck("name; DROP")
