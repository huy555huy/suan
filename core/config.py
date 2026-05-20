"""环境配置加载。从 .env 读取 LLM 端点信息。"""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


_load_env(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    llm_api_key: str = os.environ.get("LLM_API_KEY", "")
    # Model — MODEL is the single knob; MODEL_HIGH / MODEL_LOW override per-tier
    model_high: str = os.environ.get("MODEL", os.environ.get("MODEL_HIGH", "deepseek-chat"))
    model_low: str = os.environ.get("MODEL_LOW", os.environ.get("MODEL", "deepseek-chat"))
    # Optional admin token for private maintenance endpoints. Leave empty to
    # disable those endpoints on public deployments.
    admin_api_token: str = os.environ.get("ADMIN_API_TOKEN", "")
    # Storage
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    db_path: Path = Path(__file__).resolve().parent.parent / "data" / "suan.db"
    # Behavior
    request_timeout: float = 90.0
    max_retries: int = 2


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
