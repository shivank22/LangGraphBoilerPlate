#!/usr/bin/env bash
# start.sh — launch the LangGraph monolith (FastAPI + optional UIs)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# UI selection: react | streamlit | both | none  (default: both)
UI="${UI:-both}"

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

echo "[INFO]  Syncing Python dependencies with uv..."
uv sync --quiet

if [ "$UI" = "react" ] || [ "$UI" = "both" ]; then
  if [ -f "frontend/package.json" ]; then
    echo "[INFO]  Installing frontend dependencies (react-markdown, remark-gfm, github-markdown-css, ...)..."
    (cd frontend && npm install --silent)
  else
    echo "[WARN]  frontend/package.json not found — React UI will not start."
  fi
fi

# --- launch ------------------------------------------------------------------

echo ""
echo "  Starting LangGraph monolith (UI=$UI)..."
echo ""
echo "  FastAPI REST  →  http://localhost:8000"
echo "  API docs      →  http://localhost:8000/docs"
if [ "$UI" = "streamlit" ] || [ "$UI" = "both" ]; then
  echo "  Streamlit UI  →  http://localhost:8501"
fi
if [ "$UI" = "react" ] || [ "$UI" = "both" ]; then
  echo "  React UI      →  http://localhost:5173"
fi
echo ""
echo "  Press Ctrl-C to stop all servers."
echo ""

export UI
uv run python src/langgraph_app/server.py
