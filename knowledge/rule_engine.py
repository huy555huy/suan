"""Symbolic rule engine for the Suan knowledge layer.

Rules live in ``rules.json`` and are matched against a ``Charts``
dict-like object.  The engine intentionally avoids ``eval`` and
implements a tiny safe DSL:

    "<dotted.path> <operator> <value>"

Supported operators: ``==``, ``!=``, ``>``, ``<``, ``>=``, ``<=``,
``in`` and ``contains``.

Truthy combinations are expressed as ``all_of`` / ``any_of`` lists
on each rule's ``trigger`` block.

Glob-style wildcards are supported in dotted paths (e.g.
``chart.bazi.ten_gods.*``); the engine returns the *list* of values
under the wildcard so ``contains`` / ``in`` work naturally.
"""
from __future__ import annotations
import json
import os
from functools import lru_cache
from typing import Any, Iterable

# ── Loading ─────────────────────────────────────────────────
_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")


@lru_cache(maxsize=1)
def load_rules() -> list[dict]:
    """Return the parsed rule list (cached)."""
    with open(_RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Tokeniser & expression parser ───────────────────────────

_OPERATORS = ("<=", ">=", "==", "!=", "<", ">", " contains ", " in ")


def _split_top_level(expr: str) -> tuple[str, str, str] | None:
    """Split ``"path op value"`` honouring multi-char operators."""
    s = expr.strip()
    # check operators in order so that '<=' beats '<'
    for op in _OPERATORS:
        idx = _find_top_level_op(s, op)
        if idx >= 0:
            left = s[:idx].strip()
            right = s[idx + len(op):].strip()
            return left, op.strip(), right
    return None


def _find_top_level_op(s: str, op: str) -> int:
    """Find ``op`` outside of string literals or brackets."""
    in_str: str | None = None
    depth = 0
    i = 0
    L = len(s)
    while i <= L - len(op):
        ch = s[i]
        if in_str:
            if ch == "\\" and i + 1 < L:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            i += 1
            continue
        if depth == 0 and s[i:i + len(op)] == op:
            return i
        i += 1
    return -1


def _parse_value(raw: str) -> Any:
    """Convert a value literal to a Python object."""
    s = raw.strip()
    if not s:
        return None
    # quoted strings
    if (s[0] == s[-1]) and s[0] in ("'", '"') and len(s) >= 2:
        return s[1:-1]
    # boolean / null
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    # list literal
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        parts = _split_list(inner)
        return [_parse_value(p) for p in parts]
    # numeric
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s  # bare identifier — fall back to string


def _split_list(inner: str) -> list[str]:
    out: list[str] = []
    cur = []
    in_str: str | None = None
    depth = 0
    for ch in inner:
        if in_str:
            cur.append(ch)
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            cur.append(ch)
            continue
        if ch in "([{":
            depth += 1
            cur.append(ch)
            continue
        if ch in ")]}":
            depth -= 1
            cur.append(ch)
            continue
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


# ── Path resolver ──────────────────────────────────────────

_MISSING = object()


def _resolve_path(charts: Any, path: str) -> Any:
    """Walk a dotted / wildcard path through ``charts``.

    ``charts`` may be a pydantic model, a plain dict, or any nested
    combination of dicts and lists.  Wildcards (``*``) iterate over
    list items or dict values and produce a flat list of leaves.

    Returns ``_MISSING`` if any intermediate step is None or absent.
    """
    parts = path.split(".")
    # most rules start with "chart.bazi..." — strip the "chart." root
    if parts and parts[0] == "chart":
        parts = parts[1:]
    current: Any = charts
    for p in parts:
        if current is _MISSING or current is None:
            return _MISSING
        if p == "*":
            current = _expand_wildcard(current)
            continue
        current = _step(current, p)
    return current


def _step(value: Any, key: str) -> Any:
    """Single step into ``value`` by ``key``.

    Falls back to indexing for numeric keys against lists.  Treats
    pydantic models as dicts via ``.model_dump`` if available.
    """
    if value is None:
        return _MISSING
    # pydantic BaseModel → dict
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            value = value.model_dump()
        except Exception:
            pass
    # list step: numeric index, or "*" handled separately
    if isinstance(value, list):
        if key.isdigit():
            idx = int(key)
            if 0 <= idx < len(value):
                return value[idx]
            return _MISSING
        # apply key to each element and flatten dict lookups
        return [_step(item, key) for item in value]
    if isinstance(value, dict):
        if key in value:
            return value[key]
        return _MISSING
    # attribute access for arbitrary objects (e.g. raw pydantic models)
    return getattr(value, key, _MISSING)


def _expand_wildcard(value: Any) -> list[Any]:
    """Expand ``*`` over a list / dict into a flat list of values."""
    if value is None or value is _MISSING:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return list(value.values())
    return [value]


# ── Predicate evaluator ────────────────────────────────────


def _coerce_for_compare(a: Any, b: Any) -> tuple[Any, Any]:
    """Best-effort numeric coercion for comparison operators."""
    if isinstance(a, (int, float)) and isinstance(b, str):
        try:
            return a, float(b) if "." in b else int(b)
        except ValueError:
            return a, b
    if isinstance(b, (int, float)) and isinstance(a, str):
        try:
            return (float(a) if "." in a else int(a)), b
        except ValueError:
            return a, b
    return a, b


def _eval_predicate(charts: Any, predicate: str) -> bool:
    """Evaluate a single predicate string against ``charts``."""
    parsed = _split_top_level(predicate)
    if parsed is None:
        # treat as a "truthy path exists" sentinel
        val = _resolve_path(charts, predicate.strip())
        return _truthy(val)
    left, op, right = parsed
    lhs = _resolve_path(charts, left)
    rhs = _parse_value(right)
    if lhs is _MISSING:
        return False
    if op == "==":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    if op in (">", "<", ">=", "<="):
        a, b = _coerce_for_compare(lhs, rhs)
        try:
            if op == ">":
                return a > b
            if op == "<":
                return a < b
            if op == ">=":
                return a >= b
            if op == "<=":
                return a <= b
        except TypeError:
            return False
    if op == "in":
        # lhs is value, rhs is the iterable
        if not isinstance(rhs, (list, tuple, set, str)):
            return False
        return lhs in rhs
    if op == "contains":
        # lhs should be a container, rhs the probe
        if isinstance(lhs, list):
            # flatten one level for wildcard outputs
            flat: list[Any] = []
            for item in lhs:
                if isinstance(item, list):
                    flat.extend(item)
                else:
                    flat.append(item)
            return rhs in flat
        if isinstance(lhs, (str, tuple, set)):
            return rhs in lhs
        if isinstance(lhs, dict):
            return rhs in lhs or rhs in lhs.values()
        return False
    return False


def _truthy(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, (list, dict, str, tuple, set)):
        return len(value) > 0
    return bool(value)


# ── Public API ─────────────────────────────────────────────


def evaluate_rule(rule: dict, charts: Any) -> bool:
    """Return ``True`` iff every condition in the rule's trigger fires."""
    trig = rule.get("trigger") or {}
    if not isinstance(trig, dict):
        return False
    all_of: list[str] = trig.get("all_of") or []
    any_of: list[str] = trig.get("any_of") or []
    if not all_of and not any_of:
        return False
    if all_of and not all(_eval_predicate(charts, p) for p in all_of):
        return False
    if any_of and not any(_eval_predicate(charts, p) for p in any_of):
        return False
    return True


def find_matching_rules(
    charts: Any,
    system: str | None = None,
    top_k: int = 30,
    rules: list[dict] | None = None,
) -> list[dict]:
    """Return rules whose triggers match the supplied charts.

    Parameters
    ----------
    charts : Charts | dict | object
        A Charts pydantic model, the result of ``charts.model_dump()``,
        or any equivalent mapping.
    system : str | None
        Filter to a single system (``"bazi"``, ``"ziwei"`` …).
    top_k : int
        Cap the number of returned rules.
    rules : list[dict] | None
        Inject a custom ruleset (handy for tests).
    """
    pool = rules if rules is not None else load_rules()
    out: list[dict] = []
    for r in pool:
        if system and r.get("system") != system:
            continue
        try:
            if evaluate_rule(r, charts):
                out.append(r)
        except Exception:
            # swallow malformed rules — never crash the agent loop
            continue
        if len(out) >= top_k:
            break
    return out


def rules_for_system(system: str) -> list[dict]:
    """Convenience helper: every rule belonging to ``system``."""
    return [r for r in load_rules() if r.get("system") == system]


def rule_by_id(rule_id: str) -> dict | None:
    for r in load_rules():
        if r.get("rule_id") == rule_id:
            return r
    return None


__all__ = [
    "load_rules",
    "evaluate_rule",
    "find_matching_rules",
    "rules_for_system",
    "rule_by_id",
]
