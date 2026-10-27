#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Quo tells quo-bridge about missed calls (SETUP-VAL T6)
# ==========================================================================
# Run on Gerrit's laptop. Two hidden prompts, one after the other; nothing you paste is shown or saved:
#   1. a Vercel token (vercel.com > Account Settings > Tokens, your Pro team, expires in 1 day)
#   2. the Quo key (1Password: Zingas Bridge > Bridge Secrets > QUO_API_KEY)
# It puts the newest quo-bridge online, then adds "missed call" to quo-bridge's existing Quo call alert.
# Nobody gets a text. Delete the Vercel token afterwards.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

ask() {   # $1 = what to paste; prints the pasted value with spaces taken out
  echo >&2
  echo "Paste $1, then press Return. Nothing shows while you paste." >&2
  printf '> ' >&2
  IFS= read -rs V
  echo >&2
  printf '%s' "$V" | tr -d '[:space:]'
}
TOKEN="$(ask "the Vercel token you just made")"
[ -n "$TOKEN" ] || { echo "Nothing pasted. Nothing was changed." >&2; exit 1; }
KEY="$(ask "the Quo key (1Password: Zingas Bridge > Bridge Secrets > QUO_API_KEY)")"
[ -n "$KEY" ] || { echo "Nothing pasted. Nothing was changed." >&2; exit 1; }

printf '%s\n%s\n' "$TOKEN" "$KEY" | python3 -I "$HERE/quo_missed_setup.py"
unset TOKEN KEY
echo
echo "You can close this tab and delete the Vercel token."
