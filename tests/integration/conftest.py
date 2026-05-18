"""Fixtures que levantan MySQL y Postgres reales con Testcontainers.

Cada test marcado con ``@pytest.mark.integration`` consume una de estas
conexiones reales. Los contenedores se reutilizan en toda la sesión.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

import shiba

try:
    from testcontainers.mysql import MySqlContainer
    from testcontainers.postgres import PostgresContainer
except ImportError:
    MySqlContainer = None  # type: ignore[assignment,misc]
    PostgresContainer = None  # type: ignore[assignment,misc]


_SKIP_INTEGRATION = os.getenv("SHIBA_SKIP_INTEGRATION") == "1"


@pytest.fixture(scope="session")
def mysql_url() -> Iterator[str]:
    if _SKIP_INTEGRATION or MySqlContainer is None:
        pytest.skip("integration tests deshabilitados o testcontainers no instalado")
    with MySqlContainer("mysql:8.0", dialect="pymysql") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    if _SKIP_INTEGRATION or PostgresContainer is None:
        pytest.skip("integration tests deshabilitados o testcontainers no instalado")
    with PostgresContainer("postgres:16-alpine", driver=None) as container:
        yield container.get_connection_url()


def _normalize_to_shiba_dsn(url: str, scheme: str) -> str:
    """``mysql+pymysql://...`` → ``mysql://...`` (Shiba ignora el driver hint)."""
    if "+" in url.split("://", 1)[0]:
        head, tail = url.split("://", 1)
        return f"{scheme}://{tail}"
    return url


@pytest.fixture
def mysql_cx(mysql_url: str) -> Iterator[shiba.ShibaConnection]:
    dsn = _normalize_to_shiba_dsn(mysql_url, "mysql")
    cx = shiba.connect(dsn)
    try:
        yield cx
    finally:
        cx.close()


@pytest.fixture
def postgres_cx(postgres_url: str) -> Iterator[shiba.ShibaConnection]:
    dsn = _normalize_to_shiba_dsn(postgres_url, "postgres")
    cx = shiba.connect(dsn)
    try:
        yield cx
    finally:
        cx.close()
