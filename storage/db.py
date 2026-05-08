"""SQLite 持久化（异步）。

存放：
- sessions: 会话元数据
- charts: 计算盘面（JSON）— 按 PIPL 风险，本项目作为本地工具不存明文生辰
  但保留架构占位（生产环境应换 KMS 加密列）
- feedback: 用户反馈
- traces: 推理追溯
"""
from __future__ import annotations
import json
import time
from typing import Any

import aiosqlite

from core.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_name TEXT,
    scenario TEXT NOT NULL,
    question TEXT,
    birth_info TEXT,        -- JSON, 仅本地可信环境保留
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS charts (
    session_id TEXT NOT NULL,
    charts_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (session_id)
);

CREATE TABLE IF NOT EXISTS verdicts (
    session_id TEXT PRIMARY KEY,
    verdict_json TEXT NOT NULL,
    narrative TEXT,
    safety_triggers TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    rating INTEGER,
    tags TEXT,
    text TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_session ON traces(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
"""


async def init_db() -> None:
    db_path = str(settings.db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def save_session(session_id: str, user_name: str | None, scenario: str,
                        question: str, birth_info: dict) -> None:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO sessions(session_id, user_name, scenario, question, birth_info, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, user_name, scenario, question, json.dumps(birth_info, ensure_ascii=False),
             int(time.time())),
        )
        await db.commit()


async def save_charts(session_id: str, charts_json: dict) -> None:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO charts(session_id, charts_json, created_at) VALUES (?,?,?)",
            (session_id, json.dumps(charts_json, ensure_ascii=False), int(time.time())),
        )
        await db.commit()


async def save_verdict(session_id: str, verdict: dict, narrative: str,
                        safety_triggers: list[str]) -> None:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO verdicts(session_id, verdict_json, narrative, safety_triggers, created_at) "
            "VALUES (?,?,?,?,?)",
            (session_id, json.dumps(verdict, ensure_ascii=False), narrative,
             json.dumps(safety_triggers, ensure_ascii=False), int(time.time())),
        )
        await db.commit()


async def save_trace(trace_id: str, session_id: str, trace_json: dict) -> None:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO traces(trace_id, session_id, trace_json, created_at) VALUES (?,?,?,?)",
            (trace_id, session_id, json.dumps(trace_json, ensure_ascii=False), int(time.time())),
        )
        await db.commit()


async def save_feedback(session_id: str, rating: int, tags: list[str], text: str | None) -> None:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        await db.execute(
            "INSERT INTO feedback(session_id, rating, tags, text, created_at) VALUES (?,?,?,?,?)",
            (session_id, rating, json.dumps(tags, ensure_ascii=False), text, int(time.time())),
        )
        await db.commit()


async def fetch_session(session_id: str) -> dict | None:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        async with db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))


async def fetch_session_full(session_id: str) -> dict | None:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        sess = await fetch_session(session_id)
        if not sess:
            return None
        result = {"session": sess}
        for table in ("charts", "verdicts", "traces"):
            async with db.execute(f"SELECT * FROM {table} WHERE session_id=?", (session_id,)) as cur:
                rows = await cur.fetchall()
                cols = [d[0] for d in cur.description]
                result[table] = [dict(zip(cols, r)) for r in rows]
        return result


async def list_sessions(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(str(settings.db_path)) as db:
        async with db.execute(
            "SELECT session_id, user_name, scenario, question, created_at "
            "FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]
