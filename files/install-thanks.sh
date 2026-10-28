#!/bin/bash
# ==========================================================================
# Zinga's Assistant: the thank-you text after Gerrit emails an estimate (Gerrit, 2026-10-28)
# ==========================================================================
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old file
# in /root/.hermes/backups/pre-thanks-<time>/ first:
#   zingas_thanks.py     -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-thanks   (new)
#   zingas_followups.py  (also finds the new estimator's "Your proposal from Zinga's" emails)
#   plaud_pickup.py      (its great-to-meet-you draft now waits 2 hours with zingas-thanks)
#   skills followup-cadence, customer-memory, quo-texting
#   zingas-thanks.supervisor.conf -> /etc/supervisor/conf.d/
# Then restarts the follow-ups and the Plaud pickup, starts zingas-thanks, and prints only whether it worked.
# It texts nobody by itself: every thank-you waits for Gerrit's Approve tap in Val Approvals.
# START=0 copies the program files only (not the always-on setting, and restarts nothing) and runs the preview
# instead: who would get a thank-you now and Val's words for each. Nothing is sent or saved.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_thanks.py|/usr/local/lib/zingas/zingas_thanks.py|644"
  "zingas_thanks.py|/usr/local/bin/zingas-thanks|755"
  "zingas_followups.py|/usr/local/lib/zingas/zingas_followups.py|644"
  "zingas_followups.py|/usr/local/bin/zingas-followups|755"
  "plaud_pickup.py|/usr/local/lib/zingas/plaud_pickup.py|644"
  "plaud_pickup.py|/usr/local/bin/zingas-plaud|755"
  "skills/zingas/followup-cadence/SKILL.md|/root/.hermes/skills/zingas/followup-cadence/SKILL.md|644"
  "skills/zingas/customer-memory/SKILL.md|/root/.hermes/skills/zingas/customer-memory/SKILL.md|644"
  "skills/zingas/quo-texting/SKILL.md|/root/.hermes/skills/zingas/quo-texting/SKILL.md|644"
  "zingas-thanks.supervisor.conf|/etc/supervisor/conf.d/zingas-thanks.conf|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-thanks-$STAMP"
ENVS='cd /root && export HERMES_HOME=/root/.hermes ZINGAS_VAULT=/root/Documents/ZingasVault PYTHONPATH=/usr/local/lib/zingas'

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
  echo 'cd /usr/local/lib/zingas && python3 -c "import zingas_thanks, zingas_followups, plaud_pickup; print(\"the new code loads\")"'
  if [ "${START:-1}" = 0 ]; then
    echo "$ENVS"
    echo 'echo "--- who would get a thank-you now, and Val'"'"'s words (nothing is sent or saved):"; zingas-thanks preview || true'
    return
  fi
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-followups zingas-plaud | tail -2'
  echo 'sleep 8; supervisorctl status zingas-followups zingas-plaud zingas-thanks | awk "{print \$1, \$2}"'
}

if [ "${START:-1}" = 0 ]; then    # copy only: leave out the always-on setting
  KEEP=(); for f in "${FILES[@]}"; do [[ "$f" == *supervisor.conf* ]] || KEEP+=("$f"); done; FILES=("${KEEP[@]}")
fi
if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting the thank-you text on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
