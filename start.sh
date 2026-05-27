#!/usr/bin/env bash
# start.sh — launch the full LangGraph monolith (FastAPI + Streamlit)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# --- pre-flight checks -------------------------------------------------------

if [ ! -f ".env" ]; then
  echo "[ERROR] .env file not found."
  echo "        Run:  cp .env.example .env"
  echo "        Then set OPENAI_API_KEY inside .env"
  exit 1
fi

if ! grep -q "^OPENAI_API_KEY=sk-" .env 2>/dev/null; then
  echo "[WARN]  OPENAI_API_KEY in .env looks unset or uses the placeholder value."
fi

# --- sync deps ---------------------------------------------------------------

echo "[INFO]  Syncing dependencies with uv..."
uv sync --quiet

# --- launch ------------------------------------------------------------------

echo ""
echo "  Starting LangGraph monolith..."
echo ""
echo "  Streamlit UI  →  http://localhost:8501"
echo "  FastAPI REST  →  http://localhost:8000"
echo "  API docs      →  http://localhost:8000/docs"
echo ""
echo "  Press Ctrl-C to stop both servers."
echo ""

uv run python src/langgraph_app/server.py
