#!/bin/bash
# ==========================================================================
# Zinga's Assistant: the to-do list's 24-hour rule, and Val sending her to-do list to the website
# ==========================================================================
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old
# file in /root/.hermes/backups/pre-todo-post-<time>/ first:
#   zingas_todo.py                 -> /usr/local/lib/zingas/zingas_todo.py and /usr/local/bin/zingas-todo
#   skills/zingas/todo-list/SKILL.md -> /root/.hermes/skills/zingas/todo-list/SKILL.md
#   zingas-todo-post.supervisor.conf -> /etc/supervisor/conf.d/zingas-todo-post.conf   (runs the sender all the time)
# Then starts the sender, sends the list once and prints only whether it worked.
# No keys are copied: Val already reads her website key and address from 1Password.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_todo.py|/usr/local/lib/zingas/zingas_todo.py|644"
  "zingas_todo.py|/usr/local/bin/zingas-todo|755"
  "skills/zingas/todo-list/SKILL.md|/root/.hermes/skills/zingas/todo-list/SKILL.md|644"
  "zingas-todo-post.supervisor.conf|/etc/supervisor/conf.d/zingas-todo-post.conf|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-todo-post-$STAMP"

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
  echo 'supervisorctl restart zingas-todo-post | tail -1   # an already-running sender picks up the new code'
  echo 'sleep 5; supervisorctl status zingas-todo-post | awk "{print \$1, \$2}"'
  echo 'zingas-todo list | head -1'
  echo 'PYTHONPATH=/usr/local/lib/zingas zingas-todo post || true'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting the to-do list's 24-hour rule and website sender on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
