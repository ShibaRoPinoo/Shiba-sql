"""Validación de identificadores y operadores."""
from __future__ import annotations

import pytest

from shiba import error_codes
from shiba.errors import SchemaError
from shiba.identifiers import validate_identifier, validate_operator


@pytest.mark.parametrize(
    "name",
    ["users", "_private", "users.id", "schema.table", "a", "x123"],
)
def test_valid_identifiers(name: str) -> None:
    assert validate_identifier(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "users; DROP TABLE x",
        "users--",
        "1users",
        "",
        "user name",
        "users'",
        "`users`",
        "a" * 65,
    ],
)
def test_invalid_identifiers_raise(name: str) -> None:
    with pytest.raises(SchemaError) as ei:
        validate_identifier(name)
    assert ei.value.code is error_codes.INVALID_IDENTIFIER


def test_invalid_identifier_carries_details() -> None:
    with pytest.raises(SchemaError) as ei:
        validate_identifier("bad;name", kind="column")
    assert ei.value.code is error_codes.INVALID_IDENTIFIER
    assert ei.value.details["kind"] == "column"


@pytest.mark.parametrize("op", ["=", "!=", "<>", "<", ">=", "LIKE", "IN", "IS NOT"])
def test_valid_operators(op: str) -> None:
    assert validate_operator(op) == op.upper().strip() if op.isalpha() else op


@pytest.mark.parametrize("op", ["==", "; DROP", "OR 1=1", ""])
def test_invalid_operators(op: str) -> None:
    with pytest.raises(SchemaError) as ei:
        validate_operator(op)
    assert ei.value.code is error_codes.INVALID_OPERATOR
