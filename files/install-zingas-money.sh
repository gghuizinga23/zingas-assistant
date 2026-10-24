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

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "zingas_money.py|/usr/local/lib/zingas/zingas_money.py|644"
  "money_prices.json|/usr/local/lib/zingas/money_prices.json|644"
  "zingas-money.supervisor.conf|/etc/supervisor/conf.d/zingas-money.conf|644"
  "zingas_backup.py|/usr/local/lib/zingas/zingas_backup.py|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-zingas-money-$STAMP"

copy_one() {   # $1 = "src|dst|mode": keep the old file, then put the new one in place
  IFS='|' read -r src dst mode <<<"$1"
  echo 'set -e'
  echo "mkdir -p /usr/local/lib/zingas '$B'; chmod 700 '$B'"
  echo "[ -f '$dst' ] && cp -p '$dst' '$B/$(basename "$(dirname "$dst")")_$(basename "$dst")' || true"
  echo "base64 -d > '$dst.new' <<'ZINGAS_B64'"
  base64 < "$HERE/$src"
  echo "ZINGAS_B64"
  echo "chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  echo "echo 'copied $(basename "$dst")'"
}

finish() {     # the programs in /usr/local/bin are copies of the ones just put in /usr/local/lib/zingas
  echo 'set -e'
  for bin in zingas-money zingas-backup; do
    echo "[ -f /usr/local/bin/$bin ] && cp -p /usr/local/bin/$bin '$B/bin_$bin' || true"
  done
  echo 'install -m 755 /usr/local/lib/zingas/zingas_money.py /usr/local/bin/zingas-money'
  echo 'install -m 755 /usr/local/lib/zingas/zingas_backup.py /usr/local/bin/zingas-backup'
  echo "echo 'Saved the old files in $B'"
  echo 'mkdir -p /root/Documents/ZingasVault/money && chmod 700 /root/Documents/ZingasVault/money'
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-backup >/dev/null 2>&1 || true'
  echo 'sleep 5; supervisorctl status zingas-money | awk "{print \$1, \$2}"'
  echo 'zingas-money show | grep -E "^The website" || true'
  echo 'if zingas-money now >/dev/null; then echo "The website took Val'"'"'s first cost count."; else zingas-money status | grep last_error; fi'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f"; done
  finish
  exit 0
fi
echo "Putting Val's cost counter on her computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
