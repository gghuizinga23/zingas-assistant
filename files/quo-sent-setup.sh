#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Quo tells quo-bridge about texts you send yourself (one time)
# ==========================================================================
# Run on Gerrit's laptop after quo-redeploy.sh has put the newest quo-bridge online.
# Make a Vercel token first (vercel.com > Account Settings > Tokens, your Pro team, expires in 1 day).
# Both keys go into hidden prompts. They are never shown and never saved on this laptop.
# Nobody gets a text. Delete the Vercel token in Vercel afterwards.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

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

KEYS="$(hidden 'the Quo key (1Password: Zingas Bridge > Bridge Secrets > QUO_API_KEY)')"
KEYS+=$'\n'"$(hidden 'the Vercel token you just made')"
printf '%s\n' "$KEYS" | python3 -I "$HERE/quo_sent_setup.py"
unset KEYS
echo
echo "You can close this tab and delete the Vercel token."
