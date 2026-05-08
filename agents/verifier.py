"""VRP Verifier — 反思镜模式（v1.4 设计）。

设计要点：
- 仅 FACT_VIOLATION（chart_ref 真实性失败）走硬拒绝
- 其它档位（RULE_NOVEL / SOURCE_SYNTHESIZED / SEMANTIC_WEAK / OVERCLAIM）保留 + 标记 + 反思反馈
- 程序级校验先行（chart_ref path / value 严格匹配），LLM 语义校验补充
- 不阻塞主流程，让 LLM agency 与命理师认知之间形成对话
"""
from __future__ import annotations
import json
from typing import Any

from core.schemas import GroundedClaim, Charts
from core.llm_client import chat_json
from agents.prompts import VERIFIER_SYSTEM


def _resolve_path(obj: Any, path: str) -> tuple[bool, Any]:
    """逐层解析 json_path（如 'bazi.day_pillar.stem'）→ (found, value)。"""
    cur = obj
    parts = path.replace("[", ".").replace("]", "").split(".")
    for part in parts:
        if part == "":
            continue
        if part.isdigit() and isinstance(cur, list):
            idx = int(part)
            if idx >= len(cur):
                return False, None
            cur = cur[idx]
        elif isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            else:
                return False, None
        else:
            return False, None
    return True, cur


def _values_equal(expected: Any, actual: Any) -> bool:
    """宽松值比较：支持包含/相等/数值容差。"""
    if expected == actual:
        return True
    # 字符串包含
    if isinstance(expected, str) and isinstance(actual, str):
        if expected in actual or actual in expected:
            return True
    # list 包含 element
    if isinstance(actual, list):
        if expected in actual:
            return True
        if isinstance(expected, list) and all(e in actual for e in expected):
            return True
    # 数值容差
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if abs(expected - actual) <= max(1e-3, abs(expected) * 0.05):
            return True
    return False


def program_check_chart_refs(claim: GroundedClaim, charts: Charts) -> tuple[bool, str]:
    """程序级校验所有 chart_refs 的真实性。返回 (ok, reason)。"""
    if not claim.chart_refs:
        return True, "no chart_refs"
    charts_dict = charts.model_dump()
    for ref in claim.chart_refs:
        # path 可能以 "charts.bazi.xxx" 或 "bazi.xxx" 形式给出 — 兼容两者
        path = ref.json_path
        if path.startswith("charts."):
            path = path[len("charts."):]
        ok, actual = _resolve_path(charts_dict, path)
        if not ok:
            return False, f"chart_ref_path_missing: {ref.json_path}"
        if ref.expected_value is not None and not _values_equal(ref.expected_value, actual):
            # 仅当 expected_value 非 None 才严格比较
            return False, f"chart_ref_value_mismatch: {ref.json_path} expected={ref.expected_value} actual={actual}"
    return True, "all chart_refs ok"


async def verify_claim(claim: GroundedClaim, charts: Charts, *, use_llm: bool = True) -> dict:
    """对一条 claim 进行多档反馈式校验。

    返回 {verdict, reason, calibrated_confidence}。
    """
    # 1. 程序级 chart_ref 校验
    if claim.tier == "A_core":
        ok, reason = program_check_chart_refs(claim, charts)
        if not ok:
            return {"verdict": "FACT_VIOLATION", "reason": reason, "calibrated_confidence": None}

    # 2. Tier B / C 跳过严格 LLM 校验
    if claim.tier == "C_narrative":
        return {"verdict": "ACCEPT", "reason": "tier_c_pass_through", "calibrated_confidence": None}
    if claim.tier == "B_support":
        # B 类只校验上游 claim_ids 不空
        if not claim.upstream_claim_ids:
            return {"verdict": "SEMANTIC_WEAK", "reason": "tier_b_missing_upstream", "calibrated_confidence": "medium"}
        return {"verdict": "ACCEPT", "reason": "tier_b_upstream_ok", "calibrated_confidence": None}

    # 3. Tier A: 启发式预判（本地，省 LLM 钱）
    has_rule = bool(claim.rule_refs)
    has_source = bool(claim.source_refs)
    if claim.confidence == "high" and (not has_rule or not has_source):
        # 缺多源支撑但报 high 置信
        return {"verdict": "OVERCLAIM", "reason": "high_confidence_lacks_multi_source",
                "calibrated_confidence": "medium"}

    if not has_rule:
        # 没有 rule_ref 但有 source → SOURCE_SYNTHESIZED
        if has_source and len(claim.source_refs) >= 2:
            return {"verdict": "SOURCE_SYNTHESIZED", "reason": "synthesized_from_multiple_sources",
                    "calibrated_confidence": None}
        return {"verdict": "RULE_NOVEL", "reason": "no_rule_ref_provided",
                "calibrated_confidence": None}

    # 4. （可选）LLM 语义校验
    if not use_llm:
        return {"verdict": "ACCEPT", "reason": "program_checks_passed", "calibrated_confidence": None}

    user = (
        f"【Claim】{claim.claim}\n"
        f"【Tier】{claim.tier}\n"
        f"【Confidence】{claim.confidence}\n"
        f"【chart_refs】{[r.model_dump() for r in claim.chart_refs]}\n"
        f"【rule_refs】{[r.model_dump() for r in claim.rule_refs]}\n"
        f"【source_refs】{[r.model_dump() for r in claim.source_refs]}\n"
        f"【盘面摘要】{json.dumps(charts.model_dump(), ensure_ascii=False)[:1500]}\n\n"
        f"请按 Verdict 档位输出 JSON。"
    )
    try:
        parsed, _, _ = await chat_json(
            [
                {"role": "system", "content": VERIFIER_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=400,
            tier="low",
        )
    except Exception as e:
        return {"verdict": "ACCEPT", "reason": f"verifier_llm_failed:{e}", "calibrated_confidence": None}

    if not parsed or not isinstance(parsed, dict):
        return {"verdict": "ACCEPT", "reason": "verifier_no_parse", "calibrated_confidence": None}

    verdict = (parsed.get("verdict") or "ACCEPT").upper()
    if verdict not in {"ACCEPT", "FACT_VIOLATION", "RULE_NOVEL", "SOURCE_SYNTHESIZED",
                       "SEMANTIC_WEAK", "OVERCLAIM"}:
        verdict = "ACCEPT"
    return {
        "verdict": verdict,
        "reason": parsed.get("reason") or "",
        "calibrated_confidence": parsed.get("calibrated_confidence") or None,
    }


async def verify_opinion(opinion, charts: Charts, *, use_llm: bool = False) -> dict:
    """批量校验一个 ExpertOpinion 内的所有 claim。

    返回 stats dict：{total, by_verdict, fact_violations, kept}
    """
    stats = {
        "total": 0,
        "by_verdict": {},
        "fact_violations": [],
        "kept": [],
    }
    for claim in opinion.points:
        stats["total"] += 1
        result = await verify_claim(claim, charts, use_llm=use_llm)
        verdict = result["verdict"]
        stats["by_verdict"][verdict] = stats["by_verdict"].get(verdict, 0) + 1
        # 写回 verifier_verdict
        claim.verifier_verdict = verdict
        if verdict == "FACT_VIOLATION":
            stats["fact_violations"].append({"claim_id": claim.claim_id, "reason": result["reason"]})
            continue  # 硬拒绝，不加入 kept
        # 软档位：处理 calibrated_confidence
        cc = result.get("calibrated_confidence")
        if cc and cc in {"high", "medium", "low"}:
            claim.confidence = cc
        if verdict == "OVERCLAIM" and claim.confidence == "high":
            claim.confidence = "medium"
        if verdict == "SEMANTIC_WEAK" and claim.confidence == "high":
            claim.confidence = "medium"
        if verdict == "RULE_NOVEL":
            claim.deviation_note = (claim.deviation_note or "") + " [novel_application]"
        if verdict == "SOURCE_SYNTHESIZED":
            claim.deviation_note = (claim.deviation_note or "") + " [synthesized]"
        stats["kept"].append(claim)

    # 仅删除 FACT_VIOLATION 的 claim
    opinion.points = [c for c in opinion.points if c.verifier_verdict != "FACT_VIOLATION"]
    return stats
