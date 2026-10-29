"""String similarity ranking over an Arrow column, for lookups that need fuzzy matching.

DuckDB's ``jaro_winkler_similarity`` scores every value in one vectorised pass, so a fuzzy search
over half a million names takes a fraction of a second. Sources reach DuckDB only through here.
"""

import duckdb
import pyarrow as pa


def top_matches(
    values: pa.Array | pa.ChunkedArray,
    query: str,
    *,
    min_score: float,
    limit: int,
) -> list[tuple[int, float]]:
    """``(position, score)`` of the best matches of ``query`` in ``values``, best first.

    Scores are Jaro-Winkler similarities in ``[0, 1]``; only scores of at least ``min_score`` are
    returned, at most ``limit`` of them, ties broken by position. Null values never match.
    """
    table = pa.table({"i": pa.array(range(len(values)), pa.int64()), "v": values})
    con = duckdb.connect(":memory:")
    try:
        con.register("candidates", table)
        rows = con.execute(
            "SELECT i, jaro_winkler_similarity(v, ?) AS s FROM candidates "
            "WHERE s >= ? ORDER BY s DESC, i LIMIT ?",
            [query, min_score, limit],
        ).fetchall()
    finally:
        con.close()
    return [(int(i), float(s)) for i, s in rows]


__all__ = ["top_matches"]
