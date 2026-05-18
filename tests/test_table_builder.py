"""TableBuilder produce DDL coherente y mantiene su fluent API."""
from __future__ import annotations

import pytest

from shiba import error_codes
from shiba.core.table_builder import TableBuilder
from shiba.errors import MissingDataError, SchemaError


def test_basic_create(fake_db, dialect) -> None:
    sql = (
        TableBuilder(fake_db, "users", dialect=dialect)
        .increments("id", primary_key=True)
        .string("name", 20)
        .integer("age")
        .to_sql()
    )
    assert "CREATE TABLE IF NOT EXISTS `users`" in sql
    assert "`id` INT AUTO_INCREMENT PRIMARY KEY" in sql
    assert "`name` VARCHAR(20)" in sql
    assert "`age` INT" in sql


def test_unique_returns_self_fluent_chain(fake_db, dialect) -> None:
    # Regresión: v1.x unique() no retornaba self y rompía el chain.
    tb = TableBuilder(fake_db, "users", dialect=dialect).string("email").unique().not_nullable()
    assert isinstance(tb, TableBuilder)
    sql = tb.to_sql()
    assert "`email` VARCHAR(255) UNIQUE NOT NULL" in sql


def test_build_returns_self(fake_db, dialect) -> None:
    tb = TableBuilder(fake_db, "users", dialect=dialect).integer("id")
    assert tb.build() is tb


def test_enum_escapes_choices(fake_db, dialect) -> None:
    sql = (
        TableBuilder(fake_db, "u", dialect=dialect)
        .enum("status", ["active", "inactive", "O'Brien"])
        .to_sql()
    )
    assert "ENUM('active', 'inactive', 'O''Brien')" in sql


def test_invalid_column_name_raises(fake_db, dialect) -> None:
    with pytest.raises(SchemaError) as ei:
        TableBuilder(fake_db, "users", dialect=dialect).integer("id; DROP TABLE users")
    assert ei.value.code is error_codes.INVALID_IDENTIFIER


def test_build_without_columns_raises(fake_db, dialect) -> None:
    with pytest.raises(SchemaError) as ei:
        TableBuilder(fake_db, "users", dialect=dialect).build()
    assert ei.value.code is error_codes.NO_COLUMNS_DEFINED


def test_foreign_key_requires_all_params(fake_db, dialect) -> None:
    with pytest.raises(MissingDataError) as ei:
        TableBuilder(fake_db, "orders", dialect=dialect).integer("user_id").foreign()
    assert ei.value.code is error_codes.MISSING_REQUIRED_DATA


def test_foreign_key_renders(fake_db, dialect) -> None:
    sql = (
        TableBuilder(fake_db, "orders", dialect=dialect)
        .integer("user_id")
        .foreign("fk_user", "users", "id")
        .to_sql()
    )
    assert "CONSTRAINT `fk_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`)" in sql


def test_default_value_escaping(fake_db, dialect) -> None:
    sql = (
        TableBuilder(fake_db, "t", dialect=dialect)
        .string("name")
        .default("O'Brien")
        .to_sql()
    )
    assert "DEFAULT 'O''Brien'" in sql
