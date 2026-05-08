"""FastAPI 路由 + SSE 流式 + 会话管理。

支持两种使用模式：
1. 流式 (SSE)：前端先 POST 创建/更新会话档案，再发问题，再 GET stream
2. 同步 (sync)：单次提交全部 + 返回完整结果（便于深度报告 + 测试）
"""
from __future__ import annotations
import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from core.schemas import BirthInfo, Charts, AgentState
from agents.orchestrator import run_pipeline, _new_state, _charts_summary
from storage.db import (
    init_db, save_session, save_charts, save_verdict, save_trace,
    save_feedback, fetch_session_full, list_sessions,
)


router = APIRouter(prefix="/api/v1")


# ── 内存中的会话档案 + 待处理问题（演示用，生产应放 Redis）─────────
SESSION_REGISTRY: dict[str, dict] = {}
SESSION_QUEUES: dict[str, asyncio.Queue] = {}


# ── 请求模型 ──────────────────────────────────────────────────
class CreateOrUpdateSession(BaseModel):
    id: str | None = None
    name: str | None = None
    gender: str | None = "female"
    date: str | None = None        # YYYY-MM-DD
    time: str | None = None        # HH:MM
    unknownTime: bool = False
    place: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    timezone_offset: float = 8.0
    question: str | None = None
    scenario: str = "chat"


class MessageReq(BaseModel):
    text: str


class FeedbackReq(BaseModel):
    session_id: str
    rating: int = 5
    tags: list[str] = []
    text: str | None = None


# ── 会话档案管理 ─────────────────────────────────────────────
@router.post("/sessions")
async def create_or_update_session(req: CreateOrUpdateSession):
    """前端先注册档案。生辰明文仅存内存 + 不入持久化。"""
    await init_db()
    sid = req.id or f"s_{uuid.uuid4().hex[:14]}"
    SESSION_REGISTRY[sid] = req.model_dump()
    # 仅落非敏感元信息：是否填了生日/时辰；性别仅记录类别
    await save_session(
        sid, req.name, req.scenario, req.question or "",
        {"has_date": bool(req.date),
         "has_time": bool(req.time) and not req.unknownTime,
         "place": req.place,
         "gender_kind": req.gender}
    )
    return {"session_id": sid, "ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """一键销毁会话：内存 + 数据库。"""
    import aiosqlite
    from core.config import settings as _settings
    SESSION_REGISTRY.pop(session_id, None)
    SESSION_QUEUES.pop(session_id, None)
    async with aiosqlite.connect(str(_settings.db_path)) as db:
        for tab in ("verdicts", "traces", "feedback", "charts", "sessions"):
            try:
                await db.execute(f"DELETE FROM {tab} WHERE session_id = ?", (session_id,))
            except Exception:
                pass
        await db.commit()
    return {"ok": True, "deleted": session_id}


@router.delete("/sessions")
async def purge_all_sessions():
    """清空全部本地会话（用户在档案区点'清档案'时调用）。"""
    import aiosqlite
    from core.config import settings as _settings
    SESSION_REGISTRY.clear()
    SESSION_QUEUES.clear()
    async with aiosqlite.connect(str(_settings.db_path)) as db:
        for tab in ("verdicts", "traces", "feedback", "charts", "sessions"):
            try:
                await db.execute(f"DELETE FROM {tab}")
            except Exception:
                pass
        await db.commit()
    return {"ok": True, "purged": True}


def _profile_to_birthinfo(p: dict) -> tuple[BirthInfo, list[str]]:
    """把前端档案转为 BirthInfo。同时返回不确定性 caveat 列表（喂给推理）。"""
    caveats: list[str] = []

    date = p.get("date") or "2000-01-01"
    time_ = p.get("time") or "12:00"
    unknown_time = bool(p.get("unknownTime")) or not p.get("time")
    if unknown_time:
        time_ = "12:00"
        caveats.append("时辰未知（按 12:00 取值）：时柱、时支神煞、晚年大运、子女宫、ASC 与 MC、宫位划分等结论的可靠性受影响。")

    try:
        y, m, d = [int(x) for x in date.split("-")]
    except Exception:
        y, m, d = 2000, 1, 1
        caveats.append(f"生日字段解析失败（{date}）：已用 2000-01-01 代入，结论不具参考价值。")
    try:
        hh, mm = [int(x) for x in (time_ or "12:00").split(":")[:2]]
    except Exception:
        hh, mm = 12, 0

    gender = p.get("gender") or "other"
    if gender not in ("male", "female", "other"):
        gender = "other"
    if gender == "other":
        caveats.append("性别未填：按中性处理；八字大运顺逆与紫微大限方向受影响。")

    # 经纬度：用户没填则按地名查表；按"高精度 / 退化精度 / 未识"分级出 caveat
    from core.geo import resolve_geo
    lng = p.get("longitude")
    lat = p.get("latitude")
    place = p.get("place") or ""

    if (lng is None or lat is None):
        if place:
            (lng, lat), kind, matched = resolve_geo(place)
            if kind == "exact_province":
                # 精确命中省级——精度退化到省会
                caveats.append(
                    f"出生地「{place}」识别到省级（{matched}）但缺具体城市；已按省会经纬度近似（{lng:.2f}°E, {lat:.2f}°N），"
                    f"真太阳时与省内东西边缘城市差 5-15 分钟。如要更准请补具体地市。"
                )
            elif kind == "fuzzy_substring_province":
                caveats.append(
                    f"出生地「{place}」仅模糊匹配到省份（{matched}），按省会近似（{lng:.2f}°E, {lat:.2f}°N），真太阳时可能偏 5-15 分钟。"
                )
            elif kind == "fallback_beijing":
                caveats.append(
                    f"出生地「{place}」无法识别，已默认按北京（116.4°E, 39.9°N）；真太阳时可能偏差较大，建议手填经纬度或换近邻大城市重试。"
                )
            elif kind.startswith("fuzzy_"):
                # 模糊命中（"广东省东莞市" → 东莞）— 静默通过，不打扰用户
                pass
            # 其它精确命中（exact_city / exact_overseas）— 不出 caveat
        else:
            lng, lat = 116.4074, 39.9042
            caveats.append("出生地未填：默认按北京处理，真太阳时未做校正。")
    else:
        # 用户直接给了经纬度
        pass

    bi = BirthInfo(
        name=p.get("name") or None,
        gender=gender,
        year=y, month=m, day=d, hour=hh, minute=mm,
        location_name=p.get("place") or "未填",
        longitude=lng, latitude=lat,
        timezone_offset=p.get("timezone_offset") or 8.0,
        use_true_solar_time=not unknown_time,  # 时辰未知就别校正了
    )
    return bi, caveats


# 地名解析迁移到 core.geo（含 ~400 城市 + 省/海外 + 智能模糊匹配）


@router.get("/sessions")
async def list_all_sessions():
    """历史会话列表。"""
    await init_db()
    return await list_sessions(50)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    await init_db()
    full = await fetch_session_full(session_id)
    if not full:
        raise HTTPException(404, "session not found")
    return full


# ── 投递问题 + 流式接收（前端 SSE 用 GET）─────────────────────
@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: str, msg: MessageReq):
    """前端先 POST 问题，然后 GET stream 接收事件。"""
    if session_id not in SESSION_REGISTRY:
        SESSION_REGISTRY[session_id] = {"id": session_id}
    queue = SESSION_QUEUES.setdefault(session_id, asyncio.Queue())
    await queue.put({"_kind": "_question", "text": msg.text})
    return {"ok": True}


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """SSE 长连接：跑 Planner-Executor 主循环。

    多轮交互：用户首条消息触发启动；ask_user 时阻塞等下一条消息；
    所有事件都 yield 到 SSE，包括 planner_thought / ask_user / cross_link_insight / reflection / narrative_chunk 等。
    """
    from agents.planner_orchestrator import run_planner_loop

    await init_db()
    profile = SESSION_REGISTRY.get(session_id, {})
    queue = SESSION_QUEUES.setdefault(session_id, asyncio.Queue())

    async def event_stream():
        # 等用户首条消息（最多 60 秒）
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            yield _format_sse("error", {"message": "等待初始问题超时"})
            return

        if isinstance(msg, dict):
            question = msg.get("text", "")
        else:
            question = str(msg)

        try:
            birth, caveats = _profile_to_birthinfo(profile)
        except Exception as e:
            yield _format_sse("error", {"message": f"档案解析失败：{e}"})
            return

        scenario = profile.get("scenario") or "chat"
        if scenario not in ("chat", "report", "copilot"):
            scenario = "chat"

        state = _new_state(session_id, birth, question, scenario, profile.get("name"))
        state.caveats = caveats

        try:
            async for evt in run_planner_loop(state, queue, question):
                if await request.is_disconnected():
                    break
                yield _format_sse(evt["type"], evt)
                # 落库
                if evt["type"] == "chart_ready":
                    pass  # 单个 chart 不立刻落库
                if evt["type"] == "verdict_done":
                    pass
                if evt["type"] == "done":
                    # 流式正文已完，落库
                    if state.charts:
                        await save_charts(session_id,
                                          _charts_summary_brief(state.charts))
                    if state.verdict:
                        await save_verdict(session_id,
                                           state.verdict.model_dump(),
                                           state.narrative,
                                           state.safety_notes)
                    if state.trace:
                        await save_trace(state.trace.trace_id, session_id,
                                          state.trace.model_dump())
                    break  # planner 收束 → 关流
        except Exception as e:
            import traceback
            yield _format_sse("error", {"message": str(e), "trace": traceback.format_exc()[:600]})
        finally:
            # 清理队列引用（保留档案，方便用户再次进入同 session）
            SESSION_QUEUES.pop(session_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _charts_summary_brief(charts) -> dict:
    """精简的盘面摘要，供持久化使用。"""
    out = {}
    if charts.bazi:
        bz = charts.bazi
        out["bazi"] = {
            "year": f"{bz.year_pillar['stem']}{bz.year_pillar['branch']}",
            "month": f"{bz.month_pillar['stem']}{bz.month_pillar['branch']}",
            "day": f"{bz.day_pillar['stem']}{bz.day_pillar['branch']}",
            "hour": f"{bz.hour_pillar['stem']}{bz.hour_pillar['branch']}",
            "day_master": bz.day_master,
            "pattern": bz.pattern,
            "yong_shen": bz.yong_shen,
            "shen_sha": bz.shen_sha,
            "five_elements": bz.five_elements,
            "solar_term": bz.solar_term,
        }
    if charts.ziwei:
        zw = charts.ziwei
        out["ziwei"] = {"life_palace": zw.life_palace, "body_palace": zw.body_palace,
                        "five_element_bureau": zw.five_element_bureau,
                        "si_hua": zw.si_hua}
    if charts.natal_astro:
        na = charts.natal_astro
        out["natal_astro"] = {
            "sun": na.planets.get("sun", {}).get("sign"),
            "moon": na.planets.get("moon", {}).get("sign"),
            "moon_phase": na.moon_phase,
            "distributions": na.distributions,
        }
    if charts.numerology:
        nu = charts.numerology
        out["numerology"] = {"life_path": nu.life_path,
                              "expression": nu.expression,
                              "personal_year": nu.personal_year}
    if charts.tarot:
        out["tarot"] = {"spread": charts.tarot.spread,
                        "cards": [c.get("card_name") for c in charts.tarot.drawn_cards]}
    if charts.hexagram:
        hx = charts.hexagram
        out["hexagram"] = {"ben_gua": hx.ben_gua.get("name"),
                            "bian_gua": hx.bian_gua.get("name") if hx.bian_gua else None,
                            "moving_lines": hx.moving_lines}
    if charts.fengshui:
        fs = charts.fengshui
        out["fengshui"] = {"facing": fs.facing_direction, "period": fs.period,
                            "ming_gua": fs.ming_gua}
    return out


# ── 同步接口（深度报告 + 测试用）────────────────────────────
class SyncReq(BaseModel):
    profile: CreateOrUpdateSession
    question: str = ""


@router.post("/sessions/sync")
async def sync_run(req: SyncReq):
    """提交档案 + 问题，同步等待全部跑完，返回完整结构。"""
    await init_db()
    sid = req.profile.id or f"s_{uuid.uuid4().hex[:14]}"
    profile = req.profile.model_dump()
    profile["id"] = sid
    SESSION_REGISTRY[sid] = profile
    birth, caveats = _profile_to_birthinfo(profile)
    scenario = profile.get("scenario") or "chat"
    if scenario not in ("chat", "report", "copilot"):
        scenario = "chat"
    state = _new_state(sid, birth, req.question, scenario, profile.get("name"))
    state.caveats = caveats
    # 不把 birth_info 明文写库；只存元数据
    await save_session(sid, profile.get("name"), scenario, req.question,
                       {"date_present": bool(profile.get("date")),
                        "place": profile.get("place"),
                        "unknownTime": bool(profile.get("unknownTime")),
                        "caveats": caveats})

    async for _evt in run_pipeline(state):
        pass

    if state.verdict:
        await save_verdict(sid, state.verdict.model_dump(), state.narrative, state.safety_notes)
    if state.trace:
        await save_trace(state.trace.trace_id, sid, state.trace.model_dump())
    if state.charts:
        await save_charts(sid, _charts_summary(state.charts))

    return JSONResponse({
        "session_id": sid,
        "scenario": scenario,
        "narrative": state.narrative,
        "verdict": state.verdict.model_dump() if state.verdict else None,
        "charts": state.charts.model_dump(),
        "expert_opinions": [op.model_dump() for op in state.expert_opinions],
        "cn_synth": state.cn_synth.model_dump() if state.cn_synth else None,
        "wt_synth": state.wt_synth.model_dump() if state.wt_synth else None,
        "cross_alignment": state.cross_alignment.model_dump() if state.cross_alignment else None,
        "trace": state.trace.model_dump() if state.trace else None,
        "errors": state.errors,
        "caveats": caveats,
    }, media_type="application/json; charset=utf-8")


# ── 仅算盘面（不跑 LLM）────────────────────────────────────
@router.post("/charts")
async def compute_charts_only(req: SyncReq):
    """快速预览盘面，用户提交档案后即时显示。"""
    from agents.compute_dispatch import dispatch_compute
    profile = req.profile.model_dump()
    sid = profile.get("id") or f"s_preview_{uuid.uuid4().hex[:8]}"
    birth, caveats = _profile_to_birthinfo(profile)
    state = _new_state(sid, birth, req.question or "", "chat", profile.get("name"))
    state.caveats = caveats
    chart_types = ["bazi", "ziwei", "natal_astro", "numerology"]
    for ct in chart_types:
        try:
            await dispatch_compute(ct, state)
        except Exception as e:
            state.errors.append(f"{ct}:{e}")
    return JSONResponse({
        "charts": state.charts.model_dump(),
        "errors": state.errors,
        "caveats": caveats,
    }, media_type="application/json; charset=utf-8")


# ── 知识库速查（B 端 / chat 旁路调用）────────────────────────
class KnowledgeSearchReq(BaseModel):
    query: str
    system: str | None = None
    top_k: int = 8


@router.post("/knowledge/search")
async def knowledge_search(req: KnowledgeSearchReq):
    """对典籍 + 案例做 BM25-lite 检索。"""
    from knowledge.retrieval import retrieve_classics
    if not req.query or len(req.query.strip()) < 1:
        return {"results": []}
    sys_param = req.system if req.system in {
        "bazi", "ziwei", "yijing", "fengshui",
        "astrology", "tarot", "numerology"
    } else None
    results = retrieve_classics(req.query.strip(), system=sys_param, top_k=max(1, min(req.top_k, 30)))
    return {"results": results, "count": len(results)}


# ── health 别名（前端 /health 兼容）─────────────────────────
@router.get("/health")
async def api_health():
    return {"status": "ok", "service": "suan-api", "version": "1.0"}


# ── 反馈 ────────────────────────────────────────────────────
@router.post("/feedback")
async def submit_feedback(req: FeedbackReq):
    await init_db()
    await save_feedback(req.session_id, req.rating, req.tags, req.text)
    return {"ok": True}


# ── helpers ─────────────────────────────────────────────────
def _format_sse(event: str, data: Any) -> str:
    body = json.dumps(data, ensure_ascii=False, default=_json_default)
    return f"event: {event}\ndata: {body}\n\n"


def _json_default(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, BaseModel):
        return o.model_dump()
    return str(o)
