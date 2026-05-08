"""Lite retrieval over the classics knowledge base.

A pure-Python BM25-ish ranker that:

- tokenises Chinese into 1-3 character n-grams (no jieba / sklearn)
- tokenises English / pinyin / digits by whitespace + punctuation
- weights ``topic_tags`` higher than ``quote`` higher than ``summary``
- computes BM25-lite (with k1=1.5, b=0.75) over the chunk corpus

This is intentionally simple — the Suan agent runs LLM reasoning
on top of retrieved chunks, so recall > precision.
"""
from __future__ import annotations
import json
import math
import os
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from typing import Any, Iterable

_CLASSICS_PATH = os.path.join(os.path.dirname(__file__), "classics.json")

# Field weights (extra "copies" of the field added to the document
# when building the term index — heavier weight = more retrievable).
_FIELD_WEIGHTS = {
    "topic_tags": 4,
    "quote": 2,
    "summary": 2,
    "title": 2,
    "applies_when": 1,
    "school": 1,
    "system": 1,
}

# BM25 constants.
_K1 = 1.5
_B = 0.75


# ── Tokenisation ────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[\s　，。？！；：、,\.\?\!\;\:\-\—_/\\\[\]\(\)（）<>·\|]+")
_HAN_RE = re.compile(r"[一-鿿]")


def _is_han(ch: str) -> bool:
    return bool(_HAN_RE.match(ch))


def _tokenize(text: str) -> list[str]:
    """Return a list of search tokens for the input string.

    For Chinese characters we generate 1-, 2- and 3-character grams
    (so a query like ``驿马`` matches ``遇驿马``, and ``桃花劫`` matches
    ``桃花``).  Non-Han runs are split on whitespace + punctuation.
    """
    if not text:
        return []
    text = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    # Walk runs of either Han or non-Han characters.
    buf: list[str] = []
    buf_is_han: bool | None = None
    for ch in text:
        han = _is_han(ch)
        if buf_is_han is None:
            buf_is_han = han
        if han != buf_is_han:
            tokens.extend(_emit_run("".join(buf), buf_is_han))
            buf = []
            buf_is_han = han
        buf.append(ch)
    if buf:
        tokens.extend(_emit_run("".join(buf), buf_is_han or False))
    return [t for t in tokens if t]


def _emit_run(run: str, is_han: bool) -> list[str]:
    if not run:
        return []
    if is_han:
        out: list[str] = []
        # 1-grams
        out.extend(list(run))
        # 2-grams
        for i in range(len(run) - 1):
            out.append(run[i:i + 2])
        # 3-grams
        for i in range(len(run) - 2):
            out.append(run[i:i + 3])
        return out
    # non-Han run — split on punctuation / whitespace
    parts = _PUNCT_RE.split(run)
    return [p for p in parts if p]


# ── Index construction ──────────────────────────────────────


@lru_cache(maxsize=1)
def load_classics() -> list[dict]:
    """Return the parsed classics list (cached)."""
    with open(_CLASSICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _doc_text(item: dict) -> str:
    """Concatenate weighted fields into a single search document."""
    parts: list[str] = []
    for field, weight in _FIELD_WEIGHTS.items():
        val = item.get(field)
        if val is None:
            continue
        if isinstance(val, list):
            text = " ".join(str(x) for x in val)
        else:
            text = str(val)
        for _ in range(weight):
            parts.append(text)
    return " ".join(parts)


@lru_cache(maxsize=1)
def _build_index() -> dict[str, Any]:
    docs = load_classics()
    tf: list[Counter] = []
    lengths: list[int] = []
    df: Counter = Counter()
    for d in docs:
        toks = _tokenize(_doc_text(d))
        c = Counter(toks)
        tf.append(c)
        lengths.append(sum(c.values()))
        for term in c:
            df[term] += 1
    n_docs = len(docs)
    avg_len = (sum(lengths) / n_docs) if n_docs else 0.0
    idf = {
        term: math.log(1 + (n_docs - cnt + 0.5) / (cnt + 0.5))
        for term, cnt in df.items()
    }
    return {
        "tf": tf,
        "lengths": lengths,
        "idf": idf,
        "avg_len": avg_len,
        "n_docs": n_docs,
    }


def _bm25_score(query_tokens: list[str], doc_tf: Counter, doc_len: int,
                idf: dict[str, float], avg_len: float) -> float:
    score = 0.0
    if avg_len <= 0:
        return 0.0
    for term in query_tokens:
        if term not in doc_tf:
            continue
        f = doc_tf[term]
        weight = idf.get(term, 0.0)
        denom = f + _K1 * (1 - _B + _B * doc_len / avg_len)
        if denom <= 0:
            continue
        score += weight * (f * (_K1 + 1)) / denom
    return score


# ── Public retrieval API ───────────────────────────────────


def retrieve_classics(
    query: str,
    system: str | None = None,
    top_k: int = 5,
    school: str | None = None,
) -> list[dict]:
    """Return the top-k matching classics entries for ``query``.

    Parameters
    ----------
    query : str
        Free-form question or keywords (Chinese / English).
    system : str | None
        Optional filter (``"bazi"``, ``"astrology"`` …).
    top_k : int
        Maximum results.  Default 5.
    school : str | None
        Optional school filter (e.g. ``"zi_ping"``).
    """
    docs = load_classics()
    if not docs or not query:
        return []
    index = _build_index()
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    avg_len = index["avg_len"]
    idf = index["idf"]
    tf = index["tf"]
    lengths = index["lengths"]
    scored: list[tuple[float, dict]] = []
    for i, doc in enumerate(docs):
        if system and doc.get("system") != system:
            continue
        if school and doc.get("school") != school:
            continue
        s = _bm25_score(q_tokens, tf[i], lengths[i], idf, avg_len)
        if s > 0:
            scored.append((s, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:top_k]]


def search_by_tag(tag: str, top_k: int = 10) -> list[dict]:
    """Retrieve every classic whose ``topic_tags`` contains ``tag``."""
    out: list[dict] = []
    for d in load_classics():
        tags: list[str] = d.get("topic_tags") or []
        if tag in tags:
            out.append(d)
            if len(out) >= top_k:
                break
    return out


def get_classic(source_id: str) -> dict | None:
    for d in load_classics():
        if d.get("source_id") == source_id:
            return d
    return None


def iter_systems() -> Iterable[str]:
    seen: set[str] = set()
    for d in load_classics():
        sys = d.get("system")
        if sys and sys not in seen:
            seen.add(sys)
            yield sys


__all__ = [
    "load_classics",
    "retrieve_classics",
    "search_by_tag",
    "get_classic",
    "iter_systems",
]
