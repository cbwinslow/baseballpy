"""``top_matches`` ranks Arrow strings by Jaro-Winkler similarity."""

import pyarrow as pa

from baseballpy.core.similarity import top_matches


def test_best_match_first_with_limit_and_position_tie_break() -> None:
    values = pa.chunked_array([["aaron judge", "zed smith"], ["aaron judge", "aaron jungers"]])
    result = top_matches(values, "aron juge", min_score=0.5, limit=3)
    assert [position for position, _ in result][:2] == [0, 2]  # equal scores: earlier first
    assert [position for position, _ in result][2] == 3
    scores = [score for _, score in result]
    assert scores == sorted(scores, reverse=True) and all(0.5 <= s <= 1 for s in scores)
    assert len(top_matches(values, "aron juge", min_score=0.0, limit=2)) == 2


def test_threshold_nulls_and_empty_input() -> None:
    assert top_matches(pa.array(["zed smith", None]), "aron juge", min_score=0.9, limit=5) == []
    assert top_matches(pa.array([None, "x"], pa.string()), "x", min_score=0.9, limit=5) == [
        (1, 1.0)
    ]
    assert top_matches(pa.array([], pa.string()), "x", min_score=0.0, limit=5) == []
