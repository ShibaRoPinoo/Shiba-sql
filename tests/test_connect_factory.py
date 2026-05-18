"""`shiba.connect(dsn)` resuelve el dialecto desde la URL."""
from __future__ import annotations

import pytest

import shiba
from shiba import error_codes
from shiba.errors import ShibaError


def test_unsupported_scheme_raises() -> None:
    with pytest.raises(ShibaError) as ei:
        shiba.connect("oracle://u:p@h/db")
    assert ei.value.code is error_codes.NOT_IMPLEMENTED


def test_mysql_dsn_picks_mysql_dialect(monkeypatch) -> None:
    """Sin levantar conexión real, verificamos que el factory escogería MySQL."""
    constructed: dict[str, object] = {}

    class FakeMySQLDb:
        def __init__(self, host, port, user, password, *, database=None):
            constructed.update(
                kind="mysql",
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
            )

    monkeypatch.setattr(shiba, "Database", FakeMySQLDb)
    cx = shiba.connect("mysql://alice:secret@db.host:3307/app")
    assert constructed["kind"] == "mysql"
    assert constructed["host"] == "db.host"
    assert constructed["port"] == 3307
    assert constructed["user"] == "alice"
    assert constructed["database"] == "app"
    assert cx.dialect.name == "mysql"


def test_postgres_dsn_picks_postgres_dialect(monkeypatch) -> None:
    constructed: dict[str, object] = {}

    class FakePgDb:
        def __init__(self, host, port, user, password, *, database=None):
            constructed.update(
                kind="postgres",
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
            )

    # Reemplazamos el import perezoso del driver Postgres por el fake.
    import shiba.dialects.postgres.driver as pg_driver

    monkeypatch.setattr(pg_driver, "Database", FakePgDb)
    cx = shiba.connect("postgres://bob:hunter2@pg.host/app")
    assert constructed["kind"] == "postgres"
    assert constructed["host"] == "pg.host"
    assert constructed["port"] == 5432  # default
    assert constructed["user"] == "bob"
    assert constructed["database"] == "app"
    assert cx.dialect.name == "postgres"


def test_postgresql_alias() -> None:
    """``postgresql://`` y ``postgres://`` deberían comportarse igual."""
    import shiba.dialects.postgres.driver as pg_driver

    calls = []

    class FakePgDb:
        def __init__(self, *a, **kw):
            calls.append((a, kw))

    pg_driver.Database = FakePgDb  # type: ignore[misc]
    cx = shiba.connect("postgresql://x:y@h/d")
    assert cx.dialect.name == "postgres"
