#!/usr/bin/env bash
# E2E-тест интерфейса: свежая база -> сервер -> seed -> Playwright.
# Требуется: npm install playwright && npx playwright install chromium
set -euo pipefail

cd "$(dirname "$0")/../.."
PY=.venv/bin/python

# свежая база на каждый прогон — тест идемпотентен
pkill -f "[p]ython run\.py" 2>/dev/null || true
sleep 1
rm -f instance/taskboard.sqlite instance/taskboard.sqlite-*

$PY run.py > /tmp/taskboard-ui.log 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
sleep 2

$PY seed.py
node tests/ui/ui_test.mjs
