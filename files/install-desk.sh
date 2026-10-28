#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Val's desk on the website (Gerrit, 2026-10-28)
# ==========================================================================
# Run on Gerrit's laptop, after the website's desk is live (its database file ran) and quo-bridge is redeployed.
# Copies these files from this repo to Val's Orgo computer, keeping a copy of each old file in
# /root/.hermes/backups/pre-desk-<time>/ first:
#   zingas_desk.py       -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-desk   (new)
#   zingas_todo.py       (notes follow Settings > Alerts; "Is this task done too?" is also a card with Yes / No)
#   zingas_followups.py  (follows Assistant > Follow-up rules once Gerrit saves them)
#   zingas_thanks.py, zingas_installs.py, zingas_hotleads.py, zingas_inbox.py, plaud_pickup.py, quo_pickup.py,
#   zingas_sheet.py, missed_call.py   (each stops when switched off in Settings; notes copied to the website)
#   skill website-desk
#   zingas-desk.supervisor.conf -> /etc/supervisor/conf.d/
# Then restarts the programs it changed, starts zingas-desk, runs one test call and prints only whether it worked.
# It texts nobody. With nothing saved on the website yet, every program works exactly as before.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_desk.py|/usr/local/lib/zingas/zingas_desk.py|644"
  "zingas_desk.py|/usr/local/bin/zingas-desk|755"
  "zingas_todo.py|/usr/local/lib/zingas/zingas_todo.py|644"
  "zingas_todo.py|/usr/local/bin/zingas-todo|755"
  "zingas_followups.py|/usr/local/lib/zingas/zingas_followups.py|644"
  "zingas_followups.py|/usr/local/bin/zingas-followups|755"
  "zingas_thanks.py|/usr/local/lib/zingas/zingas_thanks.py|644"
  "zingas_thanks.py|/usr/local/bin/zingas-thanks|755"
  "zingas_installs.py|/usr/local/lib/zingas/zingas_installs.py|644"
  "zingas_installs.py|/usr/local/bin/zingas-installs|755"
  "zingas_hotleads.py|/usr/local/lib/zingas/zingas_hotleads.py|644"
  "zingas_hotleads.py|/usr/local/bin/zingas-hotleads|755"
  "zingas_inbox.py|/usr/local/lib/zingas/zingas_inbox.py|644"
  "zingas_inbox.py|/usr/local/bin/zingas-inbox|755"
  "plaud_pickup.py|/usr/local/lib/zingas/plaud_pickup.py|644"
  "plaud_pickup.py|/usr/local/bin/zingas-plaud|755"
  "quo_pickup.py|/usr/local/lib/zingas/quo_pickup.py|644"
  "quo_pickup.py|/usr/local/bin/zingas-quo|755"
  "zingas_sheet.py|/usr/local/lib/zingas/zingas_sheet.py|644"
  "zingas_sheet.py|/usr/local/bin/zingas-sheet|755"
  "missed_call.py|/usr/local/lib/zingas/missed_call.py|644"
  "skills/zingas/website-desk/SKILL.md|/root/.hermes/skills/zingas/website-desk/SKILL.md|644"
  "zingas-desk.supervisor.conf|/etc/supervisor/conf.d/zingas-desk.conf|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-desk-$STAMP"
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
  echo 'cd /usr/local/lib/zingas && python3 -c "import zingas_desk, zingas_todo, zingas_followups, zingas_thanks, zingas_installs, zingas_hotleads, zingas_inbox, plaud_pickup, quo_pickup, zingas_sheet, missed_call; print(\"the new code loads\")"'
  echo "$ENVS"
  echo 'zingas-desk check || true'
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-todo-post zingas-followups zingas-thanks zingas-installs zingas-hotleads zingas-inbox zingas-plaud zingas-quo-pickup zingas-sheet | tail -9'
  echo 'sleep 10; supervisorctl status | grep -E "zingas-(desk|todo-post|followups|thanks|installs|hotleads|inbox|plaud|quo-pickup|sheet) " | awk "{print \$1, \$2}"'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting Val's desk on her computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
