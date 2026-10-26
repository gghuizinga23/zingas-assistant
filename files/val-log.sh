#!/bin/bash
# Zinga's Assistant: what did Val do? Prints quo-bridge's event log, Indianapolis time. Read only.
#   bash files/val-log.sh             today
#   bash files/val-log.sh 3           the last 3 days
#   bash files/val-log.sh 1 followups only follow-up lines
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 -I "$HERE/val_log.py" "$@"
