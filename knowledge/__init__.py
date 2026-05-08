"""Knowledge layer for the Suan fortune-telling AI agent system.

This package contains the curated knowledge base used by every expert
agent during reasoning:

- ``classics.json``         original-source quotes + summaries from
                            traditional Chinese metaphysics canons and
                            Western astrology / tarot classics
- ``rules.json``            structured rule library (~60+) used by the
                            symbolic rule engine to surface candidate
                            conclusions from a chart
- ``rule_engine.py``        loads and evaluates rules against a
                            ``Charts`` object using a tiny safe DSL
- ``retrieval.py``          BM25-lite text retrieval over the classics
                            (no external deps, supports CN n-grams)
- ``tarot_meanings.py``     extended tarot context meanings (78 cards
                            x 6 contexts x upright/reversed)
- ``topics.py``             standardised cross-system topic taxonomy

Designed to be loaded once at process start and shared across the
agent graph.  No external dependencies.
"""
from __future__ import annotations
