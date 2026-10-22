#!/bin/bash
# Zinga's Assistant: Gmail part G4. Sends files/gmail_safety_check.py to Val's computer
# and runs it there. It prints OK/FAIL lines only, never a key, a link or email text.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"
{ printf "export HOME=/root HERMES_HOME=/root/.hermes PATH=/usr/local/bin:/root/.local/bin:/root/.hermes/bin:\$PATH\n"
  printf "python3 - <<'PY'\n"; cat "$HERE/gmail_safety_check.py"; printf "PY\n"; } |
  "$ORGO" computers bash "$COMPUTER"
