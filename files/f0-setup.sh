#!/bin/bash
# ==========================================================================
# Zinga's Assistant: turn on F0 quote follow-ups (text + email)
# ==========================================================================
# Run on Gerrit's laptop, once. Two keys are typed into hidden prompts and handed
# to files/f0_setup.py on stdin. They are never shown and never saved on this
# laptop. The Composio main key goes only into quo-bridge's locked Vercel
# settings (so quo-bridge can send the follow-up emails Gerrit approved); Val's
# computer never gets it. Supabase uses the Supabase app already signed in here.
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

KEYS="$(hidden 'the Composio main key (1Password: Zingas Bridge > Bridge Secrets > COMPOSIO_API_KEY)')"
KEYS+=$'\n'"$(hidden 'the Vercel token you just made')"
echo

printf '%s\n' "$KEYS" | python3 -I "$HERE/f0_setup.py" "$ORGO" "$COMPUTER"
unset KEYS
echo
echo "You can close this tab."
