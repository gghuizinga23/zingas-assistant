#!/bin/bash
# ==========================================================================
# Zinga's Assistant: missed-call text-back (plan F2)
# ==========================================================================
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old
# file in /root/.hermes/backups/pre-missed-call-<time>/ first:
#   missed_call.py  -> /usr/local/lib/zingas/missed_call.py   (new: the call-back time and Val's prompt)
#   quo_pickup.py   -> zingas-quo   (a missed call or voicemail also becomes a text-back draft)
#   skills quo-texting
# Then restarts the text pickup and prints only whether it worked. It texts nobody: every text back waits for
# Gerrit's Approve tap in Val Approvals. quo-bridge must be online first (SETUP-VAL "Missed-call text-back" T2).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "missed_call.py|/usr/local/lib/zingas/missed_call.py|644"
  "quo_pickup.py|/usr/local/lib/zingas/quo_pickup.py|644"
  "quo_pickup.py|/usr/local/bin/zingas-quo|755"
  "skills/zingas/quo-texting/SKILL.md|/root/.hermes/skills/zingas/quo-texting/SKILL.md|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-missed-call-$STAMP"

copy_one() {   # $1 = "src|dst|mode": keep the old file, then put the new one in place
  IFS='|' read -r src dst mode <<<"$1"
  echo 'set -e'
  echo "mkdir -p '$(dirname "$dst")' '$B'; chmod 700 '$B'"
  echo "[ -f '$dst' ] && cp -p '$dst' '$B/$(basename "$(dirname "$dst")")_$(basename "$dst")' || true"
  echo "base64 -d > '$dst.new' <<'ZINGAS_B64'"
  base64 < "$HERE/$src"
  echo "ZINGAS_B64"
  echo "chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  echo "echo 'copied $(basename "$dst")'"
}

finish() {
  echo "echo 'Saved the old files in $B'"
  echo 'supervisorctl restart zingas-quo-pickup | tail -1   # pick up the new code'
  echo 'sleep 8; supervisorctl status zingas-quo-pickup | awk "{print \$1, \$2}"'
  echo 'cd /usr/local/lib/zingas && python3 -c "import missed_call, quo_pickup; print(\"text-back code loads\")"'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting the missed-call text-back on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
