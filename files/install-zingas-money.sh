#!/bin/bash
# ==========================================================================
# Zinga's Assistant: put Val's hourly cost count (zingas-money) on her computer
# ==========================================================================
# Run on Gerrit's laptop. Copies these files from this repo to Val's Orgo computer, keeping a copy of each old
# file in /root/.hermes/backups/pre-zingas-money-<time>/ first:
#   zingas_money.py             -> /usr/local/lib/zingas/zingas_money.py and /usr/local/bin/zingas-money
#   money_prices.json           -> /usr/local/lib/zingas/money_prices.json   (public prices only)
#   zingas-money.supervisor.conf -> /etc/supervisor/conf.d/zingas-money.conf  (runs it all the time)
#   zingas_backup.py            -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-backup
#                                  (the nightly backup now keeps a running total of what Backblaze stores)
# Then makes the vault's money/ folder, starts the counter, sends one count and prints only whether it worked.
# No keys are copied: Val already reads her website key and address from 1Password.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

FILES=(
  "zingas_money.py|/usr/local/lib/zingas/zingas_money.py|644"
  "zingas_money.py|/usr/local/bin/zingas-money|755"
  "money_prices.json|/usr/local/lib/zingas/money_prices.json|644"
  "zingas-money.supervisor.conf|/etc/supervisor/conf.d/zingas-money.conf|644"
  "zingas_backup.py|/usr/local/lib/zingas/zingas_backup.py|644"
  "zingas_backup.py|/usr/local/bin/zingas-backup|755"
)

remote() {
  echo 'set -e'
  echo 'mkdir -p /usr/local/lib/zingas'
  echo 'B=/root/.hermes/backups/pre-zingas-money-$(date +%Y%m%d-%H%M%S); mkdir -p "$B"; chmod 700 "$B"'
  for f in "${FILES[@]}"; do
    IFS='|' read -r src dst mode <<<"$f"
    echo "[ -f '$dst' ] && cp -p '$dst' \"\$B/\$(basename '$(dirname "$dst")')_$(basename "$dst")\" || true"
    echo "base64 -d > '$dst.new' <<'ZINGAS_B64'"
    base64 < "$HERE/$src"
    echo "ZINGAS_B64"
    echo "chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  done
  echo 'echo "Saved the old files in $B"'
  echo 'mkdir -p /root/Documents/ZingasVault/money && chmod 700 /root/Documents/ZingasVault/money'
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-backup >/dev/null 2>&1 || true'
  echo 'sleep 5; supervisorctl status zingas-money | awk "{print \$1, \$2}"'
  echo 'zingas-money show | grep -E "^The website" || true'
  echo 'if zingas-money now >/dev/null; then echo "The website took Val'"'"'s first cost count."; else zingas-money status | grep last_error; fi'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  remote
  exit 0
fi
echo "Putting Val's cost counter on her computer..."
remote | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
