"""Name-search helpers for the Chadwick register: nicknames learned from the data.

A person's everyday first name often differs from the first word of their given names
(``name_first`` "Mike", ``name_given`` "Michael John"). Counting those pairs over the whole register
gives the nickname table from real data; a short fallback list covers diminutives the data lacks.
"""

import polars as pl

#: Short fallback used when the register has too little data to learn from (a small test register,
#: a partial download) and for diminutives it shows too rarely; both directions are added.
FALLBACK_NICKNAMES: dict[str, tuple[str, ...]] = {
    "mike": ("michael",),
    "joe": ("joseph",),
    "bill": ("william",),
    "billy": ("william",),
    "matt": ("matthew",),
    "jim": ("james",),
    "jimmy": ("james",),
    "bob": ("robert",),
    "rob": ("robert",),
    "tom": ("thomas",),
    "dave": ("david",),
    "dan": ("daniel",),
    "danny": ("daniel",),
    "chris": ("christopher",),
    "tony": ("anthony",),
    "steve": ("steven", "stephen"),
    "ed": ("edward", "edwin"),
    "eddie": ("edward", "edwin"),
    "pete": ("peter",),
    "fred": ("frederick",),
    "sam": ("samuel",),
    "ron": ("ronald",),
    "ronnie": ("ronald",),
    "frankie": ("francis", "franklin"),
}


def learn_nicknames(
    register: pl.DataFrame, *, min_count: int = 5, dominance: float = 0.1
) -> dict[str, tuple[str, ...]]:
    """Nickname table ``first name -> equivalent first names`` (both directions), best first.

    A pair ``(short, long)`` is kept when at least ``min_count`` people have ``short`` as
    ``name_first`` and ``long`` as the first word of ``name_given``, and it is at least ``dominance``
    times as common as the most common ``long`` for that ``short`` (this drops one-off noise such as
    a "Mike" whose given name is "George").
    """
    pairs: dict[str, dict[str, int]] = {}
    if {"name_first", "name_given"} <= set(register.columns):
        short = pl.col("name_first").str.to_lowercase().str.strip_chars()
        long_ = (
            pl.col("name_given").str.to_lowercase().str.strip_chars().str.split(" ").list.first()
        )
        counted = (
            register.filter(pl.col("name_first").is_not_null() & pl.col("name_given").is_not_null())
            .select(short.alias("short"), long_.alias("long"))
            .filter(
                (pl.col("short") != pl.col("long"))
                & (pl.col("long").str.len_chars() > pl.col("short").str.len_chars())
            )
            .group_by("short", "long")
            .len()
            .filter(pl.col("len") >= min_count)
            .with_columns(top=pl.col("len").max().over("short"))
            .filter(pl.col("len") >= dominance * pl.col("top"))
        )
        for short_name, long_name, count in counted.select("short", "long", "len").iter_rows():
            pairs.setdefault(short_name, {})[long_name] = count
            pairs.setdefault(long_name, {})[short_name] = count
    table = {
        name: tuple(sorted(others, key=lambda other: (-others[other], other)))
        for name, others in pairs.items()
    }
    for name, others in FALLBACK_NICKNAMES.items():
        for a, b in [(name, other) for other in others] + [(other, name) for other in others]:
            if b not in table.get(a, ()):
                table[a] = (*table.get(a, ()), b)
    return table


__all__ = ["FALLBACK_NICKNAMES", "learn_nicknames"]
