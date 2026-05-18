"""Quoting de identificadores Postgres (comillas dobles)."""
from __future__ import annotations

from shiba.identifiers import validate_identifier


def quote_identifier(name: str) -> str:
    """Valida y cita el identificador con comillas dobles.

    Soporta ``schema.table``, citando cada parte.
    """
    validate_identifier(name)
    return ".".join(f'"{part}"' for part in name.split("."))
