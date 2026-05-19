"""FastAPI 服务入口 — 单 Agent 架构。

启动：
    python3 server.py
    # 或
    python3 -m uvicorn server:app --reload --port 8765
"""
from __future__ import annotations
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from storage.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("suan.server")

app = FastAPI(title="算 · 中西命理 AI Agent", version="2.0")

import os as _os
_cors_extra = [o.strip() for o in (_os.environ.get("CORS_ORIGINS") or "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8765", "http://localhost:8765",
        "http://127.0.0.1", "http://localhost",
        *_cors_extra,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

WEB_ROOT = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_ROOT / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def _on_startup():
    await init_db()
    logger.info("数据库已就绪")


@app.get("/")
async def index():
    """主页：v2.html"""
    p = WEB_ROOT / "v2.html"
    if p.exists():
        return FileResponse(p)
    return RedirectResponse("/health")


@app.get("/v2")
@app.get("/v2.html")
async def v2_page():
    return FileResponse(WEB_ROOT / "v2.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "suan", "version": "2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)
