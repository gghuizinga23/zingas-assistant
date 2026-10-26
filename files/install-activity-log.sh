#!/bin/bash
# ==========================================================================
# Zinga's Assistant: put Val's activity log sender on her computer
# ==========================================================================
# Run on Gerrit's laptop (or by Claude). Copies to Val's Orgo computer, keeping a copy of any old file in
# /root/.hermes/backups/pre-activity-<time>/ first:
#   zingas_activity.py               -> /usr/local/bin/zingas-activity
#   zingas-activity.supervisor.conf  -> /etc/supervisor/conf.d/zingas-activity.conf
# Then starts it and shows its first lines. It reads her programs' logs and sends them to quo-bridge with
# the code already in /root/.hermes/quo-bridge.env. No keys are copied. Restarts no other program.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

FILES=(
  "zingas_activity.py|/usr/local/bin/zingas-activity|755"
  "zingas-activity.supervisor.conf|/etc/supervisor/conf.d/zingas-activity.conf|644"
)

remote() {
  echo 'set -e'
  echo 'B=/root/.hermes/backups/pre-activity-$(date +%Y%m%d-%H%M%S); mkdir -p "$B"; chmod 700 "$B"'
  for f in "${FILES[@]}"; do
    IFS='|' read -r src dst mode <<<"$f"
    echo "mkdir -p '$(dirname "$dst")'"
    echo "[ -f '$dst' ] && cp -p '$dst' \"\$B/$(basename "$dst")\" || true"
    echo "base64 -d > '$dst.new' <<'ZINGAS_B64'"
    base64 < "$HERE/$src"
    echo "ZINGAS_B64"
    echo "chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  done
  echo 'echo "Saved any old files in $B"'
  echo 'supervisorctl reread | tail -2; supervisorctl update zingas-activity 2>&1 | tail -2 || true'
  echo 'supervisorctl restart zingas-activity | tail -1'
  echo 'sleep 75; supervisorctl status zingas-activity | awk "{print \$1, \$2}"'
  echo 'tail -5 /var/log/orgo/zingas-activity.log; tail -5 /var/log/orgo/zingas-activity.err'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  remote
  exit 0
fi
echo "Putting Val's activity log sender on her computer..."
remote | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done."
