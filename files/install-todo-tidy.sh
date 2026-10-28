#!/bin/bash
# ==========================================================================
# Zinga's Assistant: a tidier to-do list (Gerrit's rules, 2026-10-28)
# ==========================================================================
#   - a visit puts on the list only what Gerrit said he will do and still has to do, in his own words; a step that
#     can only start after another one waits and goes on the list, as its own task, when that one is done
#   - inside each group, customers ready to buy first, then customers waiting on a quote
#   - notes name the person, never a task number; office people's jobs come from the staff list
#   - after a Done, Val asks once if a task about the same customer is done too (she closes nothing herself)
#
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old
# file in /root/.hermes/backups/pre-todo-tidy-<time>/ first, then restarts every program that uses the to-do list
# so it picks up the new code. No keys are copied.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_todo.py|/usr/local/lib/zingas/zingas_todo.py|644"
  "zingas_todo.py|/usr/local/bin/zingas-todo|755"
  "zingas_staff.json|/usr/local/lib/zingas/zingas_staff.json|644"
  "plaud_pickup.py|/usr/local/lib/zingas/plaud_pickup.py|644"
  "plaud_pickup.py|/usr/local/bin/zingas-plaud|755"
  "quo_pickup.py|/usr/local/lib/zingas/quo_pickup.py|644"
  "quo_pickup.py|/usr/local/bin/zingas-quo|755"
  "zingas_inbox.py|/usr/local/lib/zingas/zingas_inbox.py|644"
  "zingas_inbox.py|/usr/local/bin/zingas-inbox|755"
  "skills/zingas/todo-list/SKILL.md|/root/.hermes/skills/zingas/todo-list/SKILL.md|644"
  "skills/zingas/customer-memory/SKILL.md|/root/.hermes/skills/zingas/customer-memory/SKILL.md|644"
)
PROGRAMS="zingas-todo-post zingas-plaud zingas-inbox zingas-quo-pickup zingas-followups zingas-hotleads zingas-installs zingas-voice zingas-thanks"
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-todo-tidy-$STAMP"

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
  echo "PYTHONPATH=/usr/local/lib/zingas python3 -c 'import zingas_todo, plaud_pickup, quo_pickup, zingas_inbox' && echo 'the new code loads'"
  echo "supervisorctl restart $PROGRAMS | tail -9"
  echo "sleep 8; supervisorctl status $PROGRAMS | awk '{print \$1, \$2}'"
  echo 'zingas-todo list | head -1'
  echo 'PYTHONPATH=/usr/local/lib/zingas zingas-todo post || true'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting the tidier to-do list on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
