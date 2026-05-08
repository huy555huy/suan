"""FastAPI 服务入口。

启动：
    python3 -m uvicorn server:app --reload --port 8765

或直接：
    python3 server.py
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


app = FastAPI(title="算 · 中西命理 AI Agent", version="1.0")

# 默认仅允许同源（127.0.0.1 / localhost）。
# 如需别处访问，env 设 CORS_ORIGINS="http://other:port,http://x.com"
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
app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")


@app.on_event("startup")
async def _on_startup():
    await init_db()
    logger.info("数据库已就绪：%s", str(WEB_ROOT.parent / "data" / "suan.db"))


@app.get("/")
async def index():
    p = WEB_ROOT / "index.html"
    if p.exists():
        return FileResponse(p)
    return RedirectResponse("/health")


@app.get("/chat")
@app.get("/chat.html")
async def chat_page():
    return FileResponse(WEB_ROOT / "chat.html")


@app.get("/report")
@app.get("/report.html")
async def report_page():
    return FileResponse(WEB_ROOT / "report.html")


@app.get("/copilot")
@app.get("/copilot.html")
async def copilot_page():
    return FileResponse(WEB_ROOT / "copilot.html")


@app.get("/index.html")
async def index_html():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "suan", "version": "1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)
