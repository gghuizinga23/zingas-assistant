#!/bin/bash
# ==========================================================================
# Zinga's Assistant: put Val's website line (zingas-os) on her computer
# ==========================================================================
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old
# file in /root/.hermes/backups/pre-zingas-os-<time>/ first:
#   zingas_os.py          -> /usr/local/lib/zingas/zingas_os.py and /usr/local/bin/zingas-os
#   quo_pickup.py         -> /usr/local/bin/zingas-quo           (adds the Salesforce record to each draft)
#   zingas_brief_data.py  -> /root/.hermes/scripts/              (Monday numbers, and the calendar in every brief)
#   skills briefs, customer-memory, quo-texting, scheduling-handoff -> /root/.hermes/skills/zingas/
# Then restarts the text pickup and Val, and asks the website once (prints only whether it worked).
# No keys are copied: Val already reads hers from 1Password.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

FILES=(
  "zingas_os.py|/usr/local/lib/zingas/zingas_os.py|644"
  "zingas_os.py|/usr/local/bin/zingas-os|755"
  "quo_pickup.py|/usr/local/bin/zingas-quo|755"
  "zingas_brief_data.py|/root/.hermes/scripts/zingas_brief_data.py|644"
  "skills/zingas/briefs/SKILL.md|/root/.hermes/skills/zingas/briefs/SKILL.md|644"
  "skills/zingas/customer-memory/SKILL.md|/root/.hermes/skills/zingas/customer-memory/SKILL.md|644"
  "skills/zingas/quo-texting/SKILL.md|/root/.hermes/skills/zingas/quo-texting/SKILL.md|644"
  "skills/zingas/scheduling-handoff/SKILL.md|/root/.hermes/skills/zingas/scheduling-handoff/SKILL.md|644"
)

remote() {
  echo 'set -e'
  echo 'B=/root/.hermes/backups/pre-zingas-os-$(date +%Y%m%d-%H%M%S); mkdir -p "$B"; chmod 700 "$B"'
  for f in "${FILES[@]}"; do
    IFS='|' read -r src dst mode <<<"$f"
    echo "[ -f '$dst' ] && cp -p '$dst' \"\$B/\$(basename '$(dirname "$dst")')_$(basename "$dst")\" || true"
    echo "base64 -d > '$dst.new' <<'ZINGAS_B64'"
    base64 < "$HERE/$src"
    echo "ZINGAS_B64"
    echo "chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  done
  echo 'echo "Saved the old files in $B"'
  echo 'supervisorctl restart zingas-quo-pickup | tail -1'
  echo 'supervisorctl restart hermes-gateway | tail -1'
  echo 'sleep 20; supervisorctl status zingas-quo-pickup hermes-gateway | awk "{print \$1, \$2}"'
  echo 'zingas-os check'
  echo 'zingas-os appointments | head -4'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  remote
  exit 0
fi
echo "Putting Val's website line on her computer..."
remote | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
