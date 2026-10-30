#!/bin/bash
# ==========================================================================
# Zinga's Assistant: teach Val Zinga's Daily Schedule (Gerrit, 2026-10-30)
# ==========================================================================
# Run on Gerrit's laptop. Copies two files from this repo to Val's Orgo computer, keeping a copy of each old file
# in /root/.hermes/backups/pre-daily-schedule-<time>/ first:
#   skills/zingas/daily-schedule/SKILL.md -> /root/.hermes/skills/zingas/daily-schedule/SKILL.md   (new)
#   SOUL.md                               -> /root/.hermes/SOUL.md   (one new line in "Who you work for")
# Then restarts Val (hermes-gateway) so she reads them. It texts nobody and changes no program.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

FILES=(
  "skills/zingas/daily-schedule/SKILL.md|/root/.hermes/skills/zingas/daily-schedule/SKILL.md|644"
  "SOUL.md|/root/.hermes/SOUL.md|644"
)

remote() {
  echo 'set -e'
  echo 'B=/root/.hermes/backups/pre-daily-schedule-$(date +%Y%m%d-%H%M%S); mkdir -p "$B"; chmod 700 "$B"'
  for f in "${FILES[@]}"; do
    IFS='|' read -r src dst mode <<<"$f"
    echo "mkdir -p '$(dirname "$dst")'"
    echo "[ -f '$dst' ] && cp -p '$dst' \"\$B/\$(basename '$(dirname "$dst")')_$(basename "$dst")\" || true"
    echo "base64 -d > '$dst.new' <<'ZINGAS_B64'"
    base64 < "$HERE/$src"
    echo "ZINGAS_B64"
    echo "chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  done
  echo 'echo "Saved the old files in $B"'
  echo 'supervisorctl restart hermes-gateway | tail -1'
  echo 'sleep 20; supervisorctl status hermes-gateway | awk "{print \$1, \$2}"'
  echo 'sha256sum /root/.hermes/skills/zingas/daily-schedule/SKILL.md /root/.hermes/SOUL.md | cut -c1-16'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  remote
  exit 0
fi
echo "Teaching Val the daily schedule..."
remote | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. You can close this tab and tell Claude."
