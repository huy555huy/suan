"""FastAPI 路由 — 单 Agent 架构。

核心端点：
- POST /api/v1/sessions          创建/更新会话档案
- POST /api/v1/sessions/{id}/messages   投递问题
- GET  /api/v1/sessions/{id}/stream     SSE 流（agent 主循环）
- POST /api/v1/charts             纯算盘（不跑 LLM）
- POST /api/v1/daily              当日简报
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

from core.schemas import BirthInfo, Charts
from core.intake import validate_profile_for_birthinfo
from storage.db import (
    init_db, save_session, save_charts,
    save_feedback, fetch_session_full, list_sessions,
)


router = APIRouter(prefix="/api/v1")


# ── 内存会话 ─────────────────────────────────────────────────
SESSION_REGISTRY: dict[str, dict] = {}
SESSION_QUEUES: dict[str, asyncio.Queue] = {}


# ── 请求模型 ─────────────────────────────────────────────────
class CreateOrUpdateSession(BaseModel):
    id: str | None = None
    name: str | None = None
    gender: str | None = None
    date: str | None = None
    time: str | None = None
    unknownTime: bool = False
    place: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    timezone_offset: float | None = None
    use_true_solar_time: bool | None = None
    trueSolar: bool | None = None
    facing_degree: float | None = None
    move_in_year: int | None = None
    built_year: int | None = None
    hexagram_numbers: list[int] | None = None
    coin_results: list[list[int]] | None = None
    divination_time: str | None = None
    tarot_spread: str | None = None
    tarot_card_indexes: list[int] | None = None
    tarot_reversed_flags: list[bool] | None = None
    question: str | None = None
    scenario: str = "chat"


class MessageReq(BaseModel):
    text: str


class FeedbackReq(BaseModel):
    session_id: str
    rating: int = 5
    tags: list[str] = []
    text: str | None = None


# ── 档案解析 ─────────────────────────────────────────────────
def _profile_to_birthinfo(p: dict) -> tuple[BirthInfo, list[str]]:
    """把前端档案转为 BirthInfo + 不确定性 caveat 列表。"""
    caveats: list[str] = []

    date = p.get("date")
    time_ = p.get("time")
    unknown_time = bool(p.get("unknownTime")) or not p.get("time")
    strict_issues = validate_profile_for_birthinfo(p)
    if strict_issues:
        raise ValueError("；".join(issue.message for issue in strict_issues))
    if unknown_time:
        raise ValueError("出生时间缺失：不能用 12:00 或任意时辰代替；请补充精确到分钟的出生时间。")

    try:
        y, m, d = [int(x) for x in date.split("-")]
    except Exception:
        raise ValueError(f"生日字段解析失败（{date}），请使用 YYYY-MM-DD。")
    try:
        hh, mm = [int(x) for x in (time_ or "12:00").split(":")[:2]]
    except Exception:
        raise ValueError(f"出生时间解析失败（{time_}），请使用 HH:MM。")

    gender = p.get("gender") or "other"
    if gender not in ("male", "female", "other"):
        raise ValueError("性别字段只能是 male / female / other。")
    if gender == "other":
        caveats.append("性别未填：按中性处理；八字大运顺逆与紫微大限方向受影响。")

    from core.geo import infer_timezone_offset, resolve_geo
    lng = p.get("longitude")
    lat = p.get("latitude")
    place = p.get("place") or ""
    geo_kind = ""
    matched = ""

    if lng is None or lat is None:
        if place:
            (lng, lat), geo_kind, matched = resolve_geo(place)
            if geo_kind.startswith("fuzzy_substring"):
                caveats.append(f"出生地「{place}」从文本中识别到「{matched}」；若这不是出生城市/区县，请直接提供经纬度。")
            elif geo_kind == "alias":
                caveats.append(f"出生地「{place}」按别名「{matched}」匹配坐标。")
        else:
            raise ValueError("出生地未填：请补充城市/区县，或直接提供经纬度。")
    else:
        from core.geo import is_china_coordinate

        if not is_china_coordinate(float(lng), float(lat)):
            raise ValueError("当前只支持中国境内出生地；海外出生地暂不计算。")

    tz_offset = p.get("timezone_offset")
    if tz_offset is None:
        birth_local_dt = datetime(y, m, d, hh, mm)
        tz_offset, tz_confidence, tz_source = infer_timezone_offset(
            place, matched, float(lng), float(lat), birth_local_dt
        )

    place_label = place.strip() if place.strip() else f"经纬度({float(lng):.4f},{float(lat):.4f})"
    use_true_solar_time = bool(p.get("use_true_solar_time", p.get("trueSolar", True)))
    bi = BirthInfo(
        name=p.get("name") or None,
        gender=gender,
        year=y, month=m, day=d, hour=hh, minute=mm,
        location_name=place_label,
        longitude=lng, latitude=lat,
        timezone_offset=tz_offset,
        use_true_solar_time=use_true_solar_time,
    )
    return bi, caveats


# ── 会话管理 ─────────────────────────────────────────────────
@router.post("/sessions")
async def create_or_update_session(req: CreateOrUpdateSession):
    await init_db()
    sid = req.id or f"s_{uuid.uuid4().hex[:14]}"
    SESSION_REGISTRY[sid] = req.model_dump()
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


@router.get("/sessions")
async def list_all_sessions():
    await init_db()
    return await list_sessions(50)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    await init_db()
    full = await fetch_session_full(session_id)
    if not full:
        raise HTTPException(404, "session not found")
    return full


# ── 投递问题 + SSE Agent 流 ──────────────────────────────────
@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: str, msg: MessageReq):
    if session_id not in SESSION_REGISTRY:
        SESSION_REGISTRY[session_id] = {"id": session_id}
    queue = SESSION_QUEUES.setdefault(session_id, asyncio.Queue())
    await queue.put({"_kind": "_question", "text": msg.text})
    return {"ok": True}


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """SSE — 运行单 Agent 主循环。"""
    from agents.agent import run_agent_stream

    await init_db()
    profile = SESSION_REGISTRY.get(session_id, {})
    queue = SESSION_QUEUES.setdefault(session_id, asyncio.Queue())

    async def event_stream():
        # 等首条消息
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            yield _format_sse("error", {"message": "等待初始问题超时"})
            return

        question = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        try:
            birth, caveats = _profile_to_birthinfo(profile)
        except Exception as e:
            yield _format_sse("error", {"message": f"档案解析失败：{e}"})
            return

        # 跨轮上下文
        prior_context = SESSION_REGISTRY.get(session_id, {}).get("__prior_context__", "")

        try:
            final_text = ""
            charts_data = {}
            async for evt in run_agent_stream(
                birth=birth,
                question=question,
                message_queue=queue,
                caveats=caveats,
                prior_context=prior_context,
                profile=profile,
            ):
                if await request.is_disconnected():
                    break
                yield _format_sse(evt["type"], evt)

                # 收集最终文本
                if evt["type"] == "text_delta":
                    final_text += evt.get("delta", "")
                if evt["type"] == "done":
                    charts_data = evt.get("charts", {})
                    # 存跨轮摘要（精简版，不超 500 字）
                    if session_id not in SESSION_REGISTRY:
                        SESSION_REGISTRY[session_id] = {}
                    SESSION_REGISTRY[session_id]["__prior_context__"] = (
                        f"上轮问：{question[:200]}\n上轮答摘要：{final_text[:500]}"
                    )
                    # 落库
                    if charts_data:
                        await save_charts(session_id, charts_data)
                    break
        except Exception as e:
            import traceback
            yield _format_sse("error", {"message": str(e), "trace": traceback.format_exc()[:600]})
        finally:
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


# ── 纯算盘 ──────────────────────────────────────────────────
class SyncReq(BaseModel):
    profile: CreateOrUpdateSession
    question: str = ""


@router.post("/charts")
async def compute_charts_only(req: SyncReq):
    """快速算盘（不跑 LLM），用于前端即时展示。"""
    from agents.tools import ToolExecutor
    profile = req.profile.model_dump()
    try:
        birth, caveats = _profile_to_birthinfo(profile)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    charts = Charts()
    executor = ToolExecutor(birth, charts, req.question or "", profile=profile)
    errors = []
    for ct in ["bazi", "ziwei", "natal_astro", "numerology"]:
        result = await executor.dispatch("compute_chart", {"chart_type": ct})
        if result.get("error"):
            errors.append(f"{ct}:{result['error']}")
    return JSONResponse({
        "charts": charts.model_dump(),
        "errors": errors,
        "caveats": caveats,
    }, media_type="application/json; charset=utf-8")


# ── 当日简报 ─────────────────────────────────────────────────
class DailyReq(BaseModel):
    profile: CreateOrUpdateSession


@router.post("/daily")
async def daily_briefing(req: DailyReq):
    from datetime import timezone as _tz
    from computation.calendar import (
        GAN_WUXING, get_day_pillar, solar_terms_for_year, to_julian_day,
    )

    now_utc = datetime.now(_tz.utc)
    day_stem, day_branch, _ = get_day_pillar(now_utc)
    gz = day_stem + day_branch

    terms = solar_terms_for_year(now_utc.year)
    sorted_terms = sorted(terms.items(), key=lambda x: x[1])
    cur_term = "立春"
    for name, dt in reversed(sorted_terms):
        if dt <= now_utc:
            cur_term = name
            break

    jd = to_julian_day(now_utc)
    phase_frac = ((jd - 2451550.1) / 29.530589) % 1.0
    moon_names = [
        (0.03, "新月"), (0.22, "蛾眉月"), (0.28, "上弦月"),
        (0.47, "盈凸月"), (0.53, "满月"), (0.72, "亏凸月"),
        (0.78, "下弦月"), (0.97, "残月"), (1.01, "新月"),
    ]
    moon = "新月"
    for thr, nm in moon_names:
        if phase_frac < thr:
            moon = nm
            break

    day_wuxing = GAN_WUXING.get(day_stem, "土")
    fav_dir_map = {
        "木": "东 / 东南", "火": "南 / 东南", "土": "中宫 / 西南",
        "金": "西 / 西北", "水": "北 / 东北",
    }
    fav_dir = fav_dir_map.get(day_wuxing, "中宫")
    color_map = {"木": "翠玉", "火": "朱砂", "土": "鎏金", "金": "白瓷", "水": "黛青"}
    color_hex = {"木": "#5d7c6a", "火": "#c8403c", "土": "#b89968", "金": "#a09b94", "水": "#4a6670"}

    base = {
        "gz": gz, "term": cur_term, "moon": moon,
        "lucky_direction": fav_dir,
        "color_name": color_map.get(day_wuxing, "鎏金"),
        "color": color_hex.get(day_wuxing, "#b89968"),
    }

    profile = req.profile.model_dump()
    if not profile.get("date"):
        base["hint"] = f"今日 {gz}，{moon}。{cur_term} 时分。利方位：{fav_dir}。"
        return base

    try:
        from core.llm_client import chat
        sys_prompt = (
            "你是一位克制温润的命理师，给用户写一句\"今日提示\"（30-60 字内）。"
            "禁用'100%/必然/保证/改命'等绝对化语言。"
            "结合当日干支 + 节气 + 月相 + 用户档案，给一句具体的提示。"
            "不写套话；不要 markdown；不要换行。"
        )
        user_prompt = (
            f"今日 {gz}（{day_wuxing}日）· {cur_term} · {moon}\n"
            f"用户：性别 {profile.get('gender')}，生日 {profile.get('date')} {profile.get('time') or '时辰未知'}，{profile.get('place') or '出生地未填'}\n"
            f"利方位：{fav_dir} · 利色：{color_map.get(day_wuxing)}\n"
            f"输出一句话提示。"
        )
        text, _ = await chat(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": user_prompt}],
            temperature=0.6, max_tokens=180, tier="low",
        )
        base["hint"] = (text or "").strip().split("\n")[0][:140]
    except Exception:
        base["hint"] = f"今日 {gz}，{moon}。{cur_term} 时分。利方位：{fav_dir}。"

    return base


# ── 反馈 ─────────────────────────────────────────────────────
@router.post("/feedback")
async def submit_feedback(req: FeedbackReq):
    await init_db()
    await save_feedback(req.session_id, req.rating, req.tags, req.text)
    return {"ok": True}


# ── health ───────────────────────────────────────────────────
@router.get("/health")
async def api_health():
    return {"status": "ok", "service": "suan-agent", "version": "2.0"}


# ── helpers ──────────────────────────────────────────────────
def _format_sse(event: str, data: Any) -> str:
    body = json.dumps(data, ensure_ascii=False, default=_json_default)
    return f"event: {event}\ndata: {body}\n\n"


def _json_default(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, BaseModel):
        return o.model_dump()
    return str(o)
