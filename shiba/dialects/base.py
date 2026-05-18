"""Contrato común a todos los dialectos SQL.

Un :class:`Dialect` resuelve las diferencias sintácticas entre motores
(quoting de identificadores, placeholders, tipos, paginación). Los
builders del paquete :mod:`shiba.core` reciben un ``Dialect`` y producen
SQL portable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Dialect(ABC):
    """Interfaz mínima que todo dialecto debe satisfacer."""

    name: str
    """Identificador corto del dialecto (``mysql``, ``postgres``...)."""

    placeholder: str
    """Token de parámetro posicional (``%s``, ``?``, ``$1``...)."""

    @abstractmethod
    def quote_identifier(self, name: str) -> str:
        """Devuelve el identificador validado y citado."""

    @abstractmethod
    def map_type(self, declared: str) -> str:
        """Traduce un tipo canónico de Shiba al SQL del dialecto.

        ``declared`` es la cadena que produce ``TableBuilder`` (p.ej.
        ``"VARCHAR(255)"`` o ``"JSON"``). Para MySQL es identidad; para
        otros motores se traduce (``BOOLEAN`` → ``TINYINT(1)`` en MySQL
        viejo, ``JSON`` → ``JSONB`` en Postgres, etc.).
        """

    def render_limit(self, limit: int | None, offset: int | None) -> str:
        """Cláusula ``LIMIT``/``OFFSET`` del dialecto. Default ANSI-ish."""
        parts: list[str] = []
        if limit is not None:
            parts.append(f"LIMIT {int(limit)}")
        if offset is not None:
            parts.append(f"OFFSET {int(offset)}")
        return " ".join(parts)

    @abstractmethod
    def compile_upsert_update(
        self,
        update_columns: list[str],
        conflict_columns: list[str] | None = None,
    ) -> str:
        """Cláusula de resolución de conflicto para ``upsert``.

        MySQL → ``ON DUPLICATE KEY UPDATE col = VALUES(col), ...``
          (``conflict_columns`` se ignora; lo detecta por la PK).
        Postgres/SQLite → ``ON CONFLICT (col, ...) DO UPDATE SET col = EXCLUDED.col``
          (``conflict_columns`` obligatorio).
        """

    def compile_auto_increment_pk(self, column_quoted: str) -> str:
        """Declaración inline de PK auto-incremental.

        Default MySQL-ish. Postgres lo override con
        ``GENERATED ALWAYS AS IDENTITY``.
        """
        return f"{column_quoted} INT AUTO_INCREMENT PRIMARY KEY"
