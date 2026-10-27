#!/bin/bash
# ==========================================================================
# Zinga's Assistant: end-of-day wrap-up (F3), price and competitor answers (F6), after-install program (F4)
# and hot-lead alerts (F8)
# ==========================================================================
# Run on Gerrit's laptop, after the website's `val-wrapup-hotleads` change is live (the wrap-up reads the
# website's /api/assistant/day; the alerts read its proposal events). Copies these files from this repo to Val's
# Orgo computer, keeping a copy of each old file in /root/.hermes/backups/pre-four-<time>/ first:
#   zingas_wrapup.py    -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-wrapup     (new, F3)
#   value_answers.py    -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-answers    (new, F6)
#   zingas_installs.py  -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-installs   (new, F4)
#   zingas_hotleads.py  -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-hotleads   (new, F8)
#   quo_pickup.py, missed_call.py (text replies: price answers, the answer to the after-install check-in)
#   zingas_followups.py (follow-up touches: price answers)
#   zingas_brief_data.py -> /root/.hermes/scripts/   (the wrap-up and installs lines in the briefs)
#   skills briefs, zingas-voice, email-triage, after-install, hot-leads
#   zingas-installs.supervisor.conf, zingas-hotleads.supervisor.conf -> /etc/supervisor/conf.d/
# Then restarts the text pickup and the follow-ups, starts zingas-installs and zingas-hotleads, and prints only
# whether it worked. It texts nobody: every text waits for Gerrit's Approve tap in Val Approvals.
# START=0 copies the program files only (not the two always-on settings, and restarts nothing) and runs the
# previews instead: what the wrap-up would say tonight, and the Completed emails Val can match. Nothing is sent.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_wrapup.py|/usr/local/lib/zingas/zingas_wrapup.py|644"
  "zingas_wrapup.py|/usr/local/bin/zingas-wrapup|755"
  "value_answers.py|/usr/local/lib/zingas/value_answers.py|644"
  "value_answers.py|/usr/local/bin/zingas-answers|755"
  "zingas_installs.py|/usr/local/lib/zingas/zingas_installs.py|644"
  "zingas_installs.py|/usr/local/bin/zingas-installs|755"
  "zingas_hotleads.py|/usr/local/lib/zingas/zingas_hotleads.py|644"
  "zingas_hotleads.py|/usr/local/bin/zingas-hotleads|755"
  "missed_call.py|/usr/local/lib/zingas/missed_call.py|644"
  "quo_pickup.py|/usr/local/lib/zingas/quo_pickup.py|644"
  "quo_pickup.py|/usr/local/bin/zingas-quo|755"
  "zingas_followups.py|/usr/local/lib/zingas/zingas_followups.py|644"
  "zingas_followups.py|/usr/local/bin/zingas-followups|755"
  "zingas_brief_data.py|/root/.hermes/scripts/zingas_brief_data.py|644"
  "skills/zingas/briefs/SKILL.md|/root/.hermes/skills/zingas/briefs/SKILL.md|644"
  "skills/zingas/zingas-voice/SKILL.md|/root/.hermes/skills/zingas/zingas-voice/SKILL.md|644"
  "skills/zingas/email-triage/SKILL.md|/root/.hermes/skills/zingas/email-triage/SKILL.md|644"
  "skills/zingas/after-install/SKILL.md|/root/.hermes/skills/zingas/after-install/SKILL.md|644"
  "skills/zingas/hot-leads/SKILL.md|/root/.hermes/skills/zingas/hot-leads/SKILL.md|644"
  "zingas-installs.supervisor.conf|/etc/supervisor/conf.d/zingas-installs.conf|644"
  "zingas-hotleads.supervisor.conf|/etc/supervisor/conf.d/zingas-hotleads.conf|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-four-$STAMP"
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
  echo 'cd /usr/local/lib/zingas && python3 -c "import zingas_wrapup, value_answers, zingas_installs, zingas_hotleads, quo_pickup, zingas_followups; print(\"the new code loads\")"'
  if [ "${START:-1}" = 0 ]; then
    echo "$ENVS"
    echo 'echo "--- the wrap-up for today (nothing is saved):"; zingas-wrapup preview || true'
    echo 'echo "--- Completed emails and who Val matches (nothing is sent):"; zingas-installs preview || true'
    return
  fi
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-quo-pickup zingas-followups | tail -2'
  echo 'supervisorctl restart zingas-installs zingas-hotleads | tail -2'
  echo 'sleep 8; supervisorctl status zingas-quo-pickup zingas-followups zingas-installs zingas-hotleads | awk "{print \$1, \$2}"'
}

if [ "${START:-1}" = 0 ]; then    # copy only: leave out the always-on settings
  KEEP=(); for f in "${FILES[@]}"; do [[ "$f" == *supervisor.conf* ]] || KEEP+=("$f"); done; FILES=("${KEEP[@]}")
fi
if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting the wrap-up, price answers, after-install texts and hot-lead alerts on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
