"""Representación neutra de una sentencia SQL ya compilada."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SQL:
    """Una sentencia SQL lista para ejecutar.

    :param text: SQL con placeholders del dialecto correspondiente.
    :param params: parámetros (tupla para una sola ejecución, lista de
        tuplas si ``many`` es True).
    :param many: si True, ``params`` es un iterable de filas para
        ``executemany``.
    """

    text: str
    params: tuple[Any, ...] | list[tuple[Any, ...]] = field(default_factory=tuple)
    many: bool = False
