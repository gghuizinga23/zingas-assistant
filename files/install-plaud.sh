#!/bin/bash
# ==========================================================================
# Zinga's Assistant: put Plaud memory and the customer file on Val's computer (docs/VAL-BRAIN.md, Parts 1-4)
# ==========================================================================
# Run on Gerrit's laptop, only after Gerrit says yes. Copies these files from this repo to Val's Orgo computer,
# keeping a copy of each old file in /root/.hermes/backups/pre-plaud-<time>/ first:
#   zingas_customer.py    -> /usr/local/lib/zingas/            (one file per customer: profile, timeline, visits)
#   plaud_pickup.py       -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-plaud   (the recording reader)
#   quo_pickup.py         -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-quo     (texts and calls into the file)
#   zingas_inbox.py       -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-inbox   (emails into the file)
#   zingas_todo.py        -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-todo    (alerts at any hour)
#   zingas_followups.py   -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-followups (sent follow-ups into the file)
#   zingas_backup.py      -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-backup  (backs up zingas-plaud too)
#   zingas_brief_data.py  -> /root/.hermes/scripts/            (visit lines in the briefs)
#   heartbeat.sh          -> /usr/local/bin/zingas-assistant-heartbeat   (warns when the Plaud sign-in stops)
#   zingas-plaud.supervisor.conf -> /etc/supervisor/conf.d/zingas-plaud.conf
#   SOUL.md and the skills customer-memory, briefs, todo-list, quo-texting
# Then installs the official Plaud program (@plaud-ai/cli, read-only) with npm, starts zingas-plaud, restarts
# the programs that changed, and runs `zingas-plaud check`. No keys are copied. The Plaud sign-in (`plaud login`,
# step P2) is a separate step: Gerrit signs in on Val's own screen.
# DRY_RUN=1 prints what would run on Val's computer and changes nothing.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"
PLAUD_CLI="@plaud-ai/cli@0.3.15"      # pinned; checked 2026-10-24 (list, file, transcript, summary; exit 2 = sign-in)

FILES=(
  "zingas_customer.py|/usr/local/lib/zingas/zingas_customer.py|644"
  "plaud_pickup.py|/usr/local/lib/zingas/plaud_pickup.py|644"
  "plaud_pickup.py|/usr/local/bin/zingas-plaud|755"
  "quo_pickup.py|/usr/local/lib/zingas/quo_pickup.py|644"
  "quo_pickup.py|/usr/local/bin/zingas-quo|755"
  "zingas_inbox.py|/usr/local/lib/zingas/zingas_inbox.py|644"
  "zingas_inbox.py|/usr/local/bin/zingas-inbox|755"
  "zingas_todo.py|/usr/local/lib/zingas/zingas_todo.py|644"
  "zingas_todo.py|/usr/local/bin/zingas-todo|755"
  "zingas_followups.py|/usr/local/lib/zingas/zingas_followups.py|644"
  "zingas_followups.py|/usr/local/bin/zingas-followups|755"
  "zingas_backup.py|/usr/local/lib/zingas/zingas_backup.py|644"
  "zingas_backup.py|/usr/local/bin/zingas-backup|755"
  "zingas_brief_data.py|/root/.hermes/scripts/zingas_brief_data.py|644"
  "heartbeat.sh|/usr/local/bin/zingas-assistant-heartbeat|755"
  "zingas-plaud.supervisor.conf|/etc/supervisor/conf.d/zingas-plaud.conf|644"
  "SOUL.md|/root/.hermes/SOUL.md|644"
  "skills/zingas/customer-memory/SKILL.md|/root/.hermes/skills/zingas/customer-memory/SKILL.md|644"
  "skills/zingas/briefs/SKILL.md|/root/.hermes/skills/zingas/briefs/SKILL.md|644"
  "skills/zingas/todo-list/SKILL.md|/root/.hermes/skills/zingas/todo-list/SKILL.md|644"
  "skills/zingas/quo-texting/SKILL.md|/root/.hermes/skills/zingas/quo-texting/SKILL.md|644"
)

STAGE=/root/.hermes/plaud-stage
CHUNK=40000   # Orgo sends each command as one argument; Linux allows at most 128 KB per argument

stage_name() { echo "$1" | tr '/' '_'; }

# Step 1, one small call per piece: the new files wait in $STAGE. Nothing that runs is touched yet.
stage_calls() {
  local src seen=" "
  for f in "${FILES[@]}"; do
    IFS='|' read -r src _ _ <<<"$f"
    case "$seen" in *" $src "*) continue ;; esac
    seen="$seen$src "
    local b64 name
    b64=$(base64 < "$HERE/$src" | tr -d '\n')
    name=$(stage_name "$src")
    for ((i = 0; i < ${#b64}; i += CHUNK)); do
      printf "mkdir -p %s && printf '%%s' '%s' >> %s/%s.b64\n" "$STAGE" "${b64:i:CHUNK}" "$STAGE" "$name"
      printf '\0'
    done
  done
}

# Step 2, one call: keep a copy of each old file, then put each new file in place.
remote() {
  echo 'set -e'
  echo 'B=/root/.hermes/backups/pre-plaud-$(date +%Y%m%d-%H%M%S); mkdir -p "$B"; chmod 700 "$B"'
  echo 'mkdir -p /usr/local/lib/zingas /root/.hermes/scripts'
  # First check that every file arrived whole. Stop before changing anything if one did not.
  local seen=" " src dst mode name want
  for f in "${FILES[@]}"; do
    IFS='|' read -r src _ _ <<<"$f"
    case "$seen" in *" $src "*) continue ;; esac
    seen="$seen$src "
    name=$(stage_name "$src")
    want=$(shasum -a 256 < "$HERE/$src" | cut -d' ' -f1)
    echo "base64 -d < '$STAGE/$name.b64' > '$STAGE/$name'"
    echo "[ \"\$(sha256sum < '$STAGE/$name' | cut -d' ' -f1)\" = '$want' ] || { echo 'STOP: $src arrived damaged. Nothing was changed.'; rm -rf '$STAGE'; exit 1; }"
  done
  for f in "${FILES[@]}"; do
    IFS='|' read -r src dst mode <<<"$f"
    name=$(stage_name "$src")
    echo "[ -f '$dst' ] && cp -p '$dst' \"\$B/\$(basename '$(dirname "$dst")')_$(basename "$dst")\" || true"
    echo "mkdir -p '$(dirname "$dst")'"
    echo "cp '$STAGE/$name' '$dst.new' && chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  done
  echo "rm -rf '$STAGE'"
  echo 'echo "Saved the old files in $B"'
  # The official Plaud program needs Node.js 18 or newer. Stop with a clear line if it is missing.
  echo 'NODE_MAJOR=$(node -v 2>/dev/null | sed -E "s/^v([0-9]+).*/\1/" || true)'
  echo 'if [ -z "$NODE_MAJOR" ] || [ "$NODE_MAJOR" -lt 18 ]; then'
  echo '  echo "STOP: Node.js 18 or newer is missing. Tell Claude: the Plaud program needs Node.js first."'
  echo 'else'
  echo "  npm install -g --no-fund --no-audit '$PLAUD_CLI' >/dev/null && echo \"plaud program: \$(plaud version 2>/dev/null | head -1)\""
  echo 'fi'
  echo 'supervisorctl reread >/dev/null && supervisorctl update | tail -3'
  echo 'supervisorctl restart zingas-plaud zingas-quo-pickup zingas-inbox zingas-followups zingas-heartbeat zingas-backup | tail -6'
  echo 'supervisorctl restart hermes-gateway | tail -1'
  echo 'sleep 20; supervisorctl status zingas-plaud zingas-quo-pickup zingas-inbox hermes-gateway | awk "{print \$1, \$2}"'
  echo 'zingas-plaud check || true'
}

if [ "${DRY_RUN:-}" = 1 ]; then
  stage_calls | tr '\0' '\n' | cut -c1-120
  remote
  exit 0
fi
echo "Sending the new files to Val's computer (nothing changes yet)..."
"$ORGO" computers bash "$COMPUTER" -c "rm -rf '$STAGE'" >/dev/null
n=0
while IFS= read -r -d '' call; do
  out=$("$ORGO" computers bash "$COMPUTER" -c "$call" 2>&1) || { echo "STOP: sending a file failed. Nothing was changed."; echo "$out"; exit 1; }
  n=$((n + 1))
done < <(stage_calls)
echo "Sent $n pieces. Putting them in place..."
remote | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. Next is step P2 (the Plaud sign-in on Val's screen). Tell Claude."
