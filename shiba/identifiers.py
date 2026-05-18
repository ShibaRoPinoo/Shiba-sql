"""Validación de identificadores SQL.

Cualquier nombre de tabla/columna que toque la librería pasa por
:func:`validate_identifier` *antes* de concatenarse a SQL. El quoting
final (backticks, comillas dobles, corchetes) lo provee el `Dialect`.
"""
from __future__ import annotations

import re

from shiba import error_codes

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def validate_identifier(name: str, *, kind: str = "identifier") -> str:
    """Acepta el identificador o lanza :class:`SchemaError`.

    Permite nombres ``schema.table`` validando cada parte por separado.
    """
    if not isinstance(name, str) or not name:
        error_codes.INVALID_IDENTIFIER.raise_(
            f"{kind} vacío o no string: {name!r}",
            details={"kind": kind, "value": repr(name)},
        )

    for part in name.split("."):
        if not _IDENT_RE.match(part):
            error_codes.INVALID_IDENTIFIER.raise_(
                f"{kind} inválido: {name!r} "
                "(sólo [A-Za-z_][A-Za-z0-9_]*, max 64 chars)",
                details={"kind": kind, "value": name},
            )
    return name


_ALLOWED_OPERATORS = frozenset(
    {
        "=",
        "!=",
        "<>",
        "<",
        "<=",
        ">",
        ">=",
        "LIKE",
        "NOT LIKE",
        "IN",
        "NOT IN",
        "IS",
        "IS NOT",
    }
)


def validate_operator(op: str) -> str:
    """Acepta el operador o lanza :class:`SchemaError`."""
    if not isinstance(op, str):  # defensa para callers no tipados
        error_codes.INVALID_OPERATOR.raise_(  # type: ignore[unreachable]
            f"operador no string: {op!r}",
            details={"value": repr(op)},
        )
    normalized = op.strip().upper() if op.strip().isalpha() else op.strip()
    if normalized not in _ALLOWED_OPERATORS:
        error_codes.INVALID_OPERATOR.raise_(
            f"operador no permitido: {op!r}",
            details={"value": op, "allowed": sorted(_ALLOWED_OPERATORS)},
        )
    return normalized
