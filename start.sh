#!/usr/bin/env bash
# 算 suan · 启动脚本
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "[!] .env 不存在。请先创建 .env：" >&2
  echo "    LLM_BASE_URL=\"https://api.deepseek.com\"" >&2
  echo "    LLM_API_KEY=\"sk-...\"" >&2
  exit 1
fi

# 简单检查依赖
python3 -c "import openai, fastapi, uvicorn, pydantic, aiosqlite" 2>/dev/null || {
  echo "[*] 安装 Python 依赖..."
  pip3 install -r requirements.txt
}

PORT="${PORT:-8765}"
echo "[*] 启动 算 suan 服务于 http://127.0.0.1:${PORT}"
echo "    Ctrl+C 停止"
echo
exec python3 -m uvicorn server:app --host 127.0.0.1 --port "$PORT"
