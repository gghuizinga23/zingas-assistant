#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Heather's Plaud recordings into her own to-do list (files/team_plaud.py)
# ==========================================================================
# Run on Gerrit's laptop, only after Gerrit says yes, with Heather's work email:
#   HEATHER_EMAIL=heather@... bash files/install-team-plaud.sh
#   (add HEATHER_PLAUD_EMAIL=... when her Plaud account uses another email)
# Copies these files from this repo to Val's Orgo computer, keeping a copy of each old file in
# /root/.hermes/backups/pre-team-plaud-<time>/ first:
#   plaud_pickup.py   -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-plaud   (shared Plaud helpers; Gerrit's
#                        recordings work exactly as before)
#   zingas_todo.py    -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-todo    (a list per owner; Gerrit's unchanged)
#   team_plaud.py     -> /usr/local/lib/zingas/ and /usr/local/bin/zingas-team-plaud
#   zingas-team-plaud.supervisor.conf -> /etc/supervisor/conf.d/zingas-team-plaud.conf
# Then makes Heather's own Plaud sign-in folder /root/people/heather (only root can open it), writes her person
# file people/heather.json in Val's vault (only when it isn't there yet), restarts zingas-plaud and
# zingas-todo-post, starts zingas-team-plaud, and checks that all three are RUNNING.
# Heather's Plaud sign-in is a separate step she does herself (docs/SETUP-VAL.md, "Team Plaud", T2).
# No keys are copied. DRY_RUN=1 prints what would run on Val's computer and changes nothing.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"
EMAIL="$(printf '%s' "${HEATHER_EMAIL:-}" | tr 'A-Z' 'a-z')"
PLAUD_EMAIL="$(printf '%s' "${HEATHER_PLAUD_EMAIL:-}" | tr 'A-Z' 'a-z')"
EMAIL_RE='^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
if ! [[ "$EMAIL" =~ $EMAIL_RE ]]; then
  echo "STOP: give Heather's work email: HEATHER_EMAIL=heather@... bash files/install-team-plaud.sh"
  exit 1
fi
if [ -n "$PLAUD_EMAIL" ] && ! [[ "$PLAUD_EMAIL" =~ $EMAIL_RE ]]; then
  echo "STOP: HEATHER_PLAUD_EMAIL is not an email."
  exit 1
fi

# Each file goes in its own call: Orgo's helper passes a call as one argument, and Linux caps that at 128 KB.
FILES=(
  "plaud_pickup.py|/usr/local/lib/zingas/plaud_pickup.py|644"
  "plaud_pickup.py|/usr/local/bin/zingas-plaud|755"
  "zingas_todo.py|/usr/local/lib/zingas/zingas_todo.py|644"
  "zingas_todo.py|/usr/local/bin/zingas-todo|755"
  "team_plaud.py|/usr/local/lib/zingas/team_plaud.py|644"
  "team_plaud.py|/usr/local/bin/zingas-team-plaud|755"
  "zingas-team-plaud.supervisor.conf|/etc/supervisor/conf.d/zingas-team-plaud.conf|644"
)
STAMP="$(date +%Y%m%d-%H%M%S)"
B="/root/.hermes/backups/pre-team-plaud-$STAMP"

copy_one() {   # $1 = "src|dst|mode": keep the old file, check the new one arrived whole, then put it in place
  IFS='|' read -r src dst mode <<<"$1"
  local want
  want=$(shasum -a 256 < "$HERE/$src" | cut -d' ' -f1)
  echo 'set -e'
  echo "mkdir -p '$(dirname "$dst")' '$B'; chmod 700 '$B'"
  echo "[ -f '$dst' ] && cp -p '$dst' '$B/$(basename "$(dirname "$dst")")_$(basename "$dst")' || true"
  echo "base64 -d > '$dst.new' <<'ZINGAS_B64'"
  base64 < "$HERE/$src"
  echo "ZINGAS_B64"
  echo "[ \"\$(sha256sum < '$dst.new' | cut -d' ' -f1)\" = '$want' ] || { rm -f '$dst.new'; echo 'STOP: $src arrived damaged. That file was not changed.'; exit 1; }"
  echo "chmod $mode '$dst.new' && mv '$dst.new' '$dst'"
  echo "echo 'copied $(basename "$dst")'"
}

person() {     # Heather's sign-in folder and person file. An existing person file is kept as it is.
  local plaud_line=""
  [ -n "$PLAUD_EMAIL" ] && plaud_line="\"plaud_email\": \"$PLAUD_EMAIL\", "
  echo 'set -e'
  echo 'mkdir -p /root/people/heather && chmod 700 /root/people /root/people/heather'
  echo 'V=/root/Documents/ZingasVault; mkdir -p "$V/people" && chmod 700 "$V/people"'
  echo 'if [ -f "$V/people/heather.json" ]; then echo "Kept the person file that was there: people/heather.json"; else'
  echo "  printf '%s\n' '{\"name\": \"Heather Lofgren\", \"email\": \"$EMAIL\", ${plaud_line}\"plaud_home\": \"/root/people/heather\", \"list_owner\": \"heather\", \"time_zone\": \"America/Indiana/Indianapolis\"}' > \"\$V/people/heather.json\""
  echo '  chmod 600 "$V/people/heather.json"; echo "Wrote the person file people/heather.json"'
  echo 'fi'
}

finish() {
  echo "echo 'Saved the old files in $B'"
  echo 'supervisorctl reread | tail -2; supervisorctl update | tail -2'
  echo 'supervisorctl restart zingas-plaud zingas-todo-post zingas-team-plaud | tail -3   # pick up the new code'
  echo 'sleep 20; supervisorctl status zingas-plaud zingas-todo-post zingas-team-plaud | awk "{print \$1, \$2}"'
  echo 'for p in zingas-plaud zingas-todo-post zingas-team-plaud; do supervisorctl status $p | grep -q RUNNING || echo "STOP: $p is not RUNNING. Tell Claude."; done'
  echo 'zingas-plaud check | head -1 || true'
  echo 'zingas-team-plaud check || true   # says the sign-in does NOT work until Heather does T2'
}

if [ "${DRY_RUN:-}" = 1 ]; then    # show what would run on Val's computer; changes nothing
  for f in "${FILES[@]}"; do copy_one "$f" | cut -c1-160 | grep -v '^[A-Za-z0-9+/=]\{100,\}$'; done
  person
  finish
  exit 0
fi
echo "Putting Heather's Plaud to-do list on Val's computer..."
for f in "${FILES[@]}"; do
  copy_one "$f" | "$ORGO" computers bash "$COMPUTER"
done
person | "$ORGO" computers bash "$COMPUTER"
finish | "$ORGO" computers bash "$COMPUTER"
echo
echo "Done. Next: Heather's Plaud sign-in (docs/SETUP-VAL.md, Team Plaud, T2). You can close this tab and tell Claude."
