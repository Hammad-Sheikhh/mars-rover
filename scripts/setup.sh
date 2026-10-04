#!/usr/bin/env sh
# One-time Earth Station setup on macOS / Linux.
#   sh scripts/setup.sh
set -eu
cd "$(dirname "$0")/.."

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON="$candidate"; break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11 or newer is required: https://www.python.org/downloads/" >&2
  exit 1
fi
echo "Using $PYTHON"

[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[dev]"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example (defaults use the simulator)."
else
  echo ".env already exists; left unchanged. Compare it with .env.example for new settings."
fi

echo
echo "Setup done. Next:"
echo "  . .venv/bin/activate"
echo "  python -m earth_station --sim      # try it with the fake rover"
echo "  pytest                             # run the tests"
