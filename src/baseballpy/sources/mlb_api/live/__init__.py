"""Live capture of MLB games (change ``live-mlb-capture``, ADR 137 and 138).

* :mod:`.journal`: the append-only journal of every poll answer of a live game, and the HTTP wrapper that writes it;
* :mod:`.replay`: the same events again from a journal, by running the streamer's own code on the recorded answers.
"""
