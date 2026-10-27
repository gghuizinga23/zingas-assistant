#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Val keeps the Follow-Up sheet filled in (zingas-sheet, Follow-Up plan Phase 3)
# ==========================================================================
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old
# file in /root/.hermes/backups/pre-sheet-<time>/ first:
#   zingas_sheet.py  -> /usr/local/lib/zingas/zingas_sheet.py and /usr/local/bin/zingas-sheet   (new)
#   zingas_os.py, zingas_customer.py (the same as main; what zingas-sheet reads with)
#   skills followup-sheet
#   zingas-sheet.supervisor.conf -> /etc/supervisor/conf.d/zingas-sheet.conf   (runs zingas-sheet all the time)
# Then starts zingas-sheet and prints only whether it worked. It contacts no customer: it only writes to the
# website's Follow-Up sheet, where the rep always wins.
# START=0 copies the program files only (not the always-on setting) and runs "zingas-sheet preview" instead,
# which prints what Val would write and writes nothing.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_sheet.py|/usr/local/lib/zingas/zingas_sheet.py|644"
  "zingas_sheet.py|/usr/local/bin/zingas-sheet|755"
  "zingas_os.py|/usr/local/lib/zingas/zingas_os.py|644"
  "zingas_customer.py|/usr/local/lib/zingas/zingas_customer.py|644"
  "skills/zingas/followup-sheet/SKILL.md|/root/.hermes/skills/zingas/followup-sheet/SKILL.md|644"
  "zingas-sheet.supervisor.conf|/etc/supervisor/conf.d/zingas-sheet.conf|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-sheet-$STAMP"

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
  if [ "${START:-1}" = 0 ]; then
    echo 'cd /root && HERMES_HOME=/root/.hermes ZINGAS_VAULT=/root/Documents/ZingasVault PYTHONPATH=/usr/local/lib/zingas zingas-sheet preview'
    return
  fi
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-sheet | tail -1'
  echo 'sleep 8; supervisorctl status zingas-sheet | awk "{print \$1, \$2}"'
}

if [ "${START:-1}" = 0 ]; then    # copy only: leave out the always-on setting
  KEEP=(); for f in "${FILES[@]}"; do [[ "$f" == *supervisor.conf* ]] || KEEP+=("$f"); done; FILES=("${KEEP[@]}")
fi
if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting zingas-sheet (Val keeps the Follow-Up sheet) on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
