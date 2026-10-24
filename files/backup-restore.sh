#!/bin/bash
# ==========================================================================
# Zinga's Assistant: get Val's newest backup back from Backblaze B2
# ==========================================================================
# Run on Gerrit's laptop. Three things are typed into hidden prompts and handed
# to files/backup_restore.py on stdin. They are never shown and never saved.
#
#   bash files/backup-restore.sh                 test: unpack, compare, delete
#   APPLY=1 COMPUTER="<new computer>" bash files/backup-restore.sh
#                                                rebuild: put every file back
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

hidden() {   # $1 = what to paste
  local v
  echo >&2
  echo "Paste $1, then press Return. Nothing shows while you paste." >&2
  printf '> ' >&2
  IFS= read -rs v
  echo >&2
  v="$(printf '%s' "$v" | tr -d '[:space:]')"
  [ -n "$v" ] || { echo "Nothing pasted. Nothing was changed." >&2; exit 1; }
  printf '%s\n' "$v"
}

KEYS="$(hidden 'the RESTORE key ID (1Password: Zingas Bridge > Bridge Secrets > B2_RESTORE_KEY_ID)')"
KEYS+=$'\n'"$(hidden 'the RESTORE key (same note > B2_RESTORE_KEY)')"
KEYS+=$'\n'"$(hidden 'the backup password (Zingas Assistant > Assistant Secrets > BACKUP_PASSPHRASE)')"

echo
echo "Working on \"$COMPUTER\". This takes about a minute."
printf '%s\n' "$KEYS" | python3 -I "$HERE/backup_restore.py" "$ORGO" "$COMPUTER"
unset KEYS
echo
echo "You can close this tab."
