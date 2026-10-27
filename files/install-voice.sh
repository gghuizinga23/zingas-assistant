#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Val learns from what Gerrit changes in her drafts (zingas-voice)
# ==========================================================================
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old
# file in /root/.hermes/backups/pre-voice-<time>/ first:
#   zingas_voice.py      -> /usr/local/lib/zingas/zingas_voice.py and /usr/local/bin/zingas-voice   (new)
#   quo_pickup.py        -> zingas-quo        (text drafts get the lessons; saves each text pair)
#   zingas_inbox.py      -> zingas-inbox      (a sent email in the thread of Val's Gmail draft: the email pair)
#   zingas_followups.py  -> zingas-followups  (Gerrit's change to a follow-up text: a pair too)
#   skills zingas-voice, quo-texting, email-triage
#   zingas-voice.supervisor.conf -> /etc/supervisor/conf.d/zingas-voice.conf   (runs zingas-voice all the time)
# Then restarts those programs, starts zingas-voice and prints only whether it worked.
# It texts and emails nobody. Learning from edits saved before today is a separate step: zingas-voice backfill.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_voice.py|/usr/local/lib/zingas/zingas_voice.py|644"
  "zingas_voice.py|/usr/local/bin/zingas-voice|755"
  "quo_pickup.py|/usr/local/lib/zingas/quo_pickup.py|644"
  "quo_pickup.py|/usr/local/bin/zingas-quo|755"
  "zingas_inbox.py|/usr/local/lib/zingas/zingas_inbox.py|644"
  "zingas_inbox.py|/usr/local/bin/zingas-inbox|755"
  "zingas_followups.py|/usr/local/lib/zingas/zingas_followups.py|644"
  "zingas_followups.py|/usr/local/bin/zingas-followups|755"
  "skills/zingas/zingas-voice/SKILL.md|/root/.hermes/skills/zingas/zingas-voice/SKILL.md|644"
  "skills/zingas/quo-texting/SKILL.md|/root/.hermes/skills/zingas/quo-texting/SKILL.md|644"
  "skills/zingas/email-triage/SKILL.md|/root/.hermes/skills/zingas/email-triage/SKILL.md|644"
  "zingas-voice.supervisor.conf|/etc/supervisor/conf.d/zingas-voice.conf|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-voice-$STAMP"

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
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-quo-pickup zingas-inbox zingas-followups | tail -3   # pick up the new code'
  echo 'supervisorctl restart zingas-voice | tail -1'
  echo 'sleep 8; supervisorctl status zingas-voice zingas-quo-pickup zingas-inbox zingas-followups | awk "{print \$1, \$2}"'
  echo 'PYTHONPATH=/usr/local/lib/zingas zingas-voice list | wc -l | xargs echo "lessons now:"'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting zingas-voice (Val learns from your edits) on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
