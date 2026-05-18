"""Fixtures comunes — mock del Database para tests offline."""
from __future__ import annotations

from typing import Any

import pytest

from shiba.dialects.mysql import MySQLDialect


class FakeDatabase:
    """Captura las queries ejecutadas sin tocar MySQL."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, bool]] = []
        self.result: list[dict[str, Any]] = []

    def execute(
        self,
        query: str,
        params: Any = None,
        *,
        many: bool = False,
    ) -> list[dict[str, Any]]:
        self.calls.append((query, params, many))
        return self.result

    @property
    def last_call(self) -> tuple[str, Any, bool]:
        return self.calls[-1]


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def dialect() -> MySQLDialect:
    return MySQLDialect()
