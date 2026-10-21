#!/bin/bash
# Zinga's Assistant: Quo part Q6. Sends files/quo_safety_check.py to Val's computer
# and runs it there. It prints OK/FAIL lines only, never a key or a code.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"
{ printf "export HOME=/root HERMES_HOME=/root/.hermes PATH=/usr/local/bin:/root/.local/bin:/root/.hermes/bin:\$PATH\n"
  printf "python3 - <<'PY'\n"; cat "$HERE/quo_safety_check.py"; printf "PY\n"; } |
  "$ORGO" computers bash "$COMPUTER"
