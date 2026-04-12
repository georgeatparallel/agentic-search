#!/usr/bin/env bash
# setup.sh — one-shot setup and launch for Agentic Search
# Usage: bash setup.sh

set -e

# Always run from the project root (script's directory)
cd "$(dirname "$0")"

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${BOLD}${GREEN}[✓]${RESET} $*"; }
warn()    { echo -e "${BOLD}${YELLOW}[!]${RESET} $*"; }
error()   { echo -e "${BOLD}${RED}[✗]${RESET} $*"; exit 1; }
section() { echo -e "\n${BOLD}$*${RESET}"; }

# ── 1. Python version ────────────────────────────────────────────────────────
section "Checking Python..."
if ! command -v python3 &>/dev/null; then
  error "Python 3 not found. Install Python 3.11+ from https://python.org"
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  error "Python 3.11+ required, found $PY_VER"
fi
info "Python $PY_VER"

# ── 2. Poetry ────────────────────────────────────────────────────────────────
section "Checking Poetry..."
if ! command -v poetry &>/dev/null; then
  warn "Poetry not found. Installing..."
  curl -sSL https://install.python-poetry.org | python3 -
  export PATH="$HOME/.local/bin:$PATH"
fi
info "Poetry $(poetry --version | awk '{print $3}')"

# ── 3. Install Python dependencies ──────────────────────────────────────────
section "Installing Python dependencies..."
poetry install --no-root
info "Dependencies installed"

# ── 4. .env file ────────────────────────────────────────────────────────────
section "Setting up environment..."
if [ ! -f .env ]; then
  cat > .env <<'EOF'
# Required: Get a free key at https://brave.com/search/api/
BRAVE_API_KEY=

# Optional overrides (defaults shown)
# LLM_MODEL=qwen2.5:3b
# SEARCH_NUM_RESULTS=6
# AGENT_MAX_ITERATIONS=2
EOF
  warn ".env created. Add your BRAVE_API_KEY before searching."
  warn "  → Get a free key: https://brave.com/search/api/"
else
  info ".env already exists"
fi

# Check if BRAVE_API_KEY is set
if [ -f .env ]; then
  BRAVE_KEY=$(grep -E '^BRAVE_API_KEY=.+' .env | cut -d= -f2 | tr -d '[:space:]')
fi
if [ -z "${BRAVE_KEY}" ] && [ -z "${BRAVE_API_KEY}" ]; then
  warn "BRAVE_API_KEY is not set. Search will fall back to DuckDuckGo (less reliable)."
fi

# ── 5. Ollama ────────────────────────────────────────────────────────────────
section "Checking Ollama..."
if ! command -v ollama &>/dev/null; then
  warn "Ollama not found. Installing..."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v brew &>/dev/null; then
      brew install ollama
    else
      error "Homebrew not found. Install Ollama manually from https://ollama.com/download"
    fi
  elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    curl -fsSL https://ollama.com/install.sh | sh
  else
    error "Unsupported OS. Install Ollama manually from https://ollama.com/download"
  fi
fi
info "Ollama $(ollama --version 2>/dev/null | awk '{print $2}' || echo 'installed')"

# Start ollama serve if not already running
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
  warn "Starting Ollama server..."
  ollama serve &>/dev/null &
  OLLAMA_PID=$!
  # Wait for it to become ready
  for i in {1..15}; do
    sleep 1
    if curl -s http://localhost:11434/api/tags &>/dev/null; then break; fi
    if [ "$i" -eq 15 ]; then error "Ollama failed to start. Run 'ollama serve' manually."; fi
  done
  info "Ollama server started (PID $OLLAMA_PID)"
else
  info "Ollama server already running"
fi

# Pull model if not already downloaded
MODEL="qwen2.5:3b"
if ! ollama list 2>/dev/null | grep -q "$MODEL"; then
  info "Pulling $MODEL (~1.9 GB, this may take a few minutes)..."
  ollama pull "$MODEL"
else
  info "Model $MODEL already available"
fi

# ── 6. Launch server ─────────────────────────────────────────────────────────
section "Starting Agentic Search server..."
info "Server running at http://localhost:8000"
info "Press Ctrl+C to stop"
echo ""
poetry run python main.py
