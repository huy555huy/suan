#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${SUAN_DEPLOY_REMOTE:-ubuntu@1.116.115.142}"
REMOTE_DIR="${SUAN_DEPLOY_DIR:-/home/ubuntu/suan}"
SYNC_ENV=0

usage() {
  cat <<EOF
Usage:
  scripts/deploy.sh          Deploy code, preserving server data and .env
  scripts/deploy.sh --env    Also upload local .env and restart

Environment overrides:
  SUAN_DEPLOY_REMOTE=ubuntu@1.116.115.142
  SUAN_DEPLOY_DIR=/home/ubuntu/suan
EOF
}

for arg in "$@"; do
  case "$arg" in
    --env) SYNC_ENV=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

cd "$ROOT"

echo "==> Deploying to $REMOTE:$REMOTE_DIR"

rsync -az --delete \
  --exclude='.git/' \
  --include='.env.example' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*/__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='.DS_Store' \
  --exclude='data/*.db' \
  --exclude='data/*.db-*' \
  --exclude='data/cache/' \
  --exclude='data/runs/' \
  --exclude='logs/' \
  --exclude='*.log' \
  --exclude='web/static/img/tarot/*.jpg' \
  ./ "$REMOTE:$REMOTE_DIR/"

if [[ "$SYNC_ENV" == "1" ]]; then
  if [[ ! -f .env ]]; then
    echo "Local .env not found; cannot sync --env" >&2
    exit 1
  fi
  echo "==> Uploading .env"
  scp -q .env "$REMOTE:$REMOTE_DIR/.env.tmp"
  ssh "$REMOTE" "cd '$REMOTE_DIR' && install -m 600 .env.tmp .env && rm -f .env.tmp"
fi

echo "==> Installing dependencies and restarting"
ssh "$REMOTE" "set -e; cd '$REMOTE_DIR'; .venv/bin/python -m pip install -r requirements.txt >/tmp/suan-pip-install.log 2>&1; sudo systemctl restart suan; sleep 2; sudo systemctl is-active suan; curl -sS --max-time 8 http://127.0.0.1:8765/health; echo"

echo "==> Public health check"
curl -sS --max-time 8 "http://1.116.115.142:8765/health"
echo
