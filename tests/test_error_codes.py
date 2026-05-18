"""Catálogo de error codes y mapper desde drivers nativos."""
from __future__ import annotations

import pytest

from shiba import error_codes
from shiba.errors import (
    ConnectionError,
    IntegrityError,
    QueryError,
    ShibaError,
)


def test_code_uniqueness() -> None:
    seen: set[str] = set()
    for code in error_codes.ALL_CODES:
        assert code.code.startswith("SHIBA-")
        assert code.code not in seen
        seen.add(code.code)


def test_build_and_raise_attach_code() -> None:
    exc = error_codes.INTEGRITY_DUPLICATE_KEY.build("dup", query="INSERT ...", params=(1,))
    assert isinstance(exc, IntegrityError)
    assert exc.code is error_codes.INTEGRITY_DUPLICATE_KEY
    assert exc.query == "INSERT ..."
    assert exc.params == (1,)
    assert str(exc).startswith("[SHIBA-4001]")


def test_raise_helper_raises_right_class() -> None:
    with pytest.raises(ConnectionError) as ei:
        error_codes.CONNECTION_REFUSED.raise_(details={"host": "x"})
    assert ei.value.code is error_codes.CONNECTION_REFUSED
    assert ei.value.details == {"host": "x"}


def test_shiba_error_to_dict() -> None:
    exc = error_codes.UNKNOWN_COLUMN.build("col foo missing", query="SELECT foo FROM t")
    d = exc.to_dict()
    assert d == {
        "code": "SHIBA-2003",
        "name": "UNKNOWN_COLUMN",
        "message": "col foo missing",
        "details": {},
    }


def test_lookup_by_code_and_name() -> None:
    assert error_codes.BY_CODE["SHIBA-4001"] is error_codes.INTEGRITY_DUPLICATE_KEY
    assert error_codes.BY_NAME["INTEGRITY_DUPLICATE_KEY"] is error_codes.INTEGRITY_DUPLICATE_KEY


def test_mysql_errno_mapping() -> None:
    class FakeMySQLError(Exception):
        pass

    exc = FakeMySQLError(1062, "Duplicate entry")
    assert error_codes.from_driver_exception(exc) is error_codes.INTEGRITY_DUPLICATE_KEY


def test_unknown_driver_error_falls_back() -> None:
    class WeirdError(Exception):
        pass

    assert error_codes.from_driver_exception(WeirdError("?")) is error_codes.QUERY_EXECUTION_FAILED


def test_shibaerror_is_base() -> None:
    exc = error_codes.QUERY_SYNTAX_ERROR.build()
    assert isinstance(exc, ShibaError)
    assert isinstance(exc, QueryError)
