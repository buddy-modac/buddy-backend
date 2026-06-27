#!/usr/bin/env bash
# install.sh — one-step setup for PersonaForge on macOS (and Linux).
#
#   chmod +x install.sh && ./install.sh
#
# Creates a local virtualenv, installs the package editable, and runs the
# self-check. Safe to re-run.

set -e

echo "PersonaForge installer"
echo "----------------------"

# pick python
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "✗ python3 not found. On macOS: install from python.org or 'brew install python'."
  exit 1
fi
echo "Using: $($PY --version)"

# create venv
if [ ! -d ".venv" ]; then
  echo "Creating virtualenv at .venv ..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# upgrade pip quietly
python -m pip install --upgrade pip >/dev/null

# install editable with optional extras
echo "Installing PersonaForge (editable) ..."
if [ "${1:-}" = "--all" ]; then
  pip install -e ".[all]"
else
  pip install -e ".[test]"
  echo "  (core + test installed. For live web/API: ./install.sh --all)"
fi

echo
echo "Running self-check ..."
python -m personaforge.check || true

echo
echo "Done. To verify or launch:"
echo "    source .venv/bin/activate"
echo "    python -m personaforge.check     # offline self-check (no API key)"
echo "    ./start.sh                        # install + launch API server (one-shot)"
