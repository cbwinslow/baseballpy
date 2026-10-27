"""SQL identifier and literal helpers (validate, never interpolate raw user input)."""

import re

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name: str) -> str:
    """Validate and double-quote a (optionally schema-qualified) SQL identifier.

    Raises ``ValueError`` for anything that is not ``name`` or ``schema.name`` made of
    letters, digits and underscores (so injection attempts never reach the database).
    """
    parts = name.split(".")
    if not 1 <= len(parts) <= 2 or not all(_IDENT.match(p) for p in parts):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return ".".join(f'"{p}"' for p in parts)


def quote_literal(value: str) -> str:
    """Return ``value`` as a single-quoted SQL string literal with quotes escaped."""
    return "'" + value.replace("'", "''") + "'"
