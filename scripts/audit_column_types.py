"""Find text columns that hold only numbers or dates (dev tool; AGENTS.md section 3: strongly typed).

    uv run python scripts/audit_column_types.py [--source retrosheet --source statcast] [--home PATH]

For every registered dataset of the chosen sources, every column typed ``string`` is tested over a sample of
the lake's rows. A column is reported when every non-empty value is a whole number (written back exactly, so
leading zeros such as line scores stay text), a decimal number, or a date (``YYYYMMDD`` or ``YYYY-MM-DD``).
A finding is a question, not always a defect: play text, identifiers and notes can look numeric. Known
answers live in ``KNOWN_TEXT`` with the reason; anything else should be typed or explained in the source page.
"""

import argparse
from dataclasses import dataclass

import duckdb

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.sources import catalog

#: (dataset key, column) -> why the text type is right although the values look numeric
KNOWN_TEXT: dict[tuple[str, str], str] = {
    **{
        (
            f"retrosheet.{dataset}",
            f"inn{i}",
        ): "line score: x means the inning was not played, ? unknown"
        for dataset in ("manager_logs", "negro_team_stats")
        for i in range(1, 29)
    },
    (
        "retrosheet.transactions",
        "primary_date",
    ): "partial dates exist (a 00 month or day means not known)",
    (
        "retrosheet.transactions",
        "secondary_date",
    ): "partial dates exist (same format as primary_date)",
    (
        "retrosheet.events",
        "BAT_PLAY_TX",
    ): "play text: the fielders involved (a play description, not a number)",
    ("retrosheet.events_deduced", "BAT_PLAY_TX"): "play text",
    ("retrosheet.events_postseason", "BAT_PLAY_TX"): "play text",
    ("retrosheet.events", "RUN1_PLAY_TX"): "play text",
    ("retrosheet.events", "RUN3_PLAY_TX"): "play text",
    ("retrosheet.events_deduced", "RUN1_PLAY_TX"): "play text",
    ("retrosheet.events_postseason", "RUN3_PLAY_TX"): "play text",
    (
        "retrosheet.schedule",
        "makeup_date",
    ): "free text in a few rows (a date plus a note, or two dates)",
    ("retrosheet.reference_biofile0", "birthdate"): "partial dates exist (year only)",
    ("retrosheet.reference_biofile0", "deathdate"): "partial dates exist (year only)",
    ("statcast.pitches", "sv_id"): "an identifier (yymmdd_hhmmss) that DuckDB reads as a number",
    ("statcast.pitches_minors", "sv_id"): "an identifier (yymmdd_hhmmss)",
}


@dataclass(frozen=True)
class Finding:
    """A text column whose sampled values are all of one typed kind."""

    column: str
    kind: str  # int, float or date
    non_null: int


def quote_ident(name: str) -> str:
    """A double-quoted SQL identifier (column names such as ``1b_ump_id`` start with a digit)."""
    return '"' + name.replace('"', '""') + '"'


def find_typed_text_columns(
    con: duckdb.DuckDBPyConnection,
    view: str,
    columns: list[str],
    *,
    sample: int = 150_000,
    min_values: int = 20,
) -> list[Finding]:
    """The ``columns`` of ``view`` whose non-empty text values are all whole numbers, decimals or dates."""
    if not columns:
        return []
    parts = []
    for i, column in enumerate(columns):
        c = quote_ident(column)
        parts.append(
            f"count(NULLIF({c}, '')) AS n_{i}, "
            f"count(*) FILTER (WHERE {c} <> '' AND CAST(TRY_CAST({c} AS BIGINT) AS VARCHAR) = {c}) AS i_{i}, "
            f"count(*) FILTER (WHERE {c} <> '' AND TRY_CAST({c} AS DOUBLE) IS NOT NULL "
            f"AND NOT regexp_matches({c}, '^-?0[0-9]')) AS f_{i}, "
            f"count(*) FILTER (WHERE {c} <> '' AND (TRY_STRPTIME({c}, '%Y%m%d') IS NOT NULL "
            f"OR TRY_CAST({c} AS DATE) IS NOT NULL) AND length({c}) >= 8) AS d_{i}"
        )
    # Cast to text: a view may already hold a number for a column the registry still calls text.
    cast = ", ".join(f"CAST({quote_ident(c)} AS VARCHAR) AS {quote_ident(c)}" for c in columns)
    query = f"SELECT {', '.join(parts)} FROM (SELECT {cast} FROM {quote_ident(view)} USING SAMPLE {int(sample)} ROWS)"  # noqa: S608
    row = con.execute(query).fetchone()
    if row is None:  # an empty view
        return []
    found = []
    for i, column in enumerate(columns):
        n, whole, decimal, dated = row[4 * i : 4 * i + 4]
        if n < min_values:
            continue
        if dated == n:
            found.append(Finding(column, "date", n))
        elif whole == n:
            found.append(Finding(column, "int", n))
        elif decimal == n:
            found.append(Finding(column, "float", n))
    return found


def main() -> None:
    """Audit the lake and print the findings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--home", default=None)
    args = parser.parse_args()
    catalog.register_all()
    config = LakeConfig(home=args.home) if args.home else LakeConfig()
    con = duckdb.connect(str(config.database_path), read_only=True)
    total = open_questions = 0
    for spec in sorted(DATASETS.values(), key=lambda s: s.key):
        if args.source and spec.source not in args.source:
            continue
        strings = [f.name for f in spec.schema if str(f.type) in ("string", "large_string")]
        try:
            findings = find_typed_text_columns(con, spec.view, strings)
        except duckdb.CatalogException:
            continue  # the lake does not hold this dataset
        except duckdb.InvalidInputException as exc:
            print(f"UNREADABLE {spec.key}: {str(exc).splitlines()[0][:160]}")
            continue
        for finding in findings:
            total += 1
            why = KNOWN_TEXT.get((spec.key, finding.column))
            if why is None:
                open_questions += 1
            print(
                f"{'known' if why else 'TYPE?'} {spec.key}.{finding.column}: text, all {finding.kind} "
                f"({finding.non_null:,} values){' - ' + why if why else ''}"
            )
    print(f"{total} text column(s) look typed; {open_questions} without a recorded reason")


if __name__ == "__main__":
    main()
