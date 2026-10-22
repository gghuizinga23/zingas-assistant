#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Quo part Q5 (put quo-bridge online and connect it)
# ==========================================================================
# Run on Gerrit's laptop. Three keys are typed into hidden prompts and handed to
# files/quo_setup.py on stdin. They are never shown and never saved on this
# laptop. Supabase uses the Supabase app already signed in here, so no Supabase
# token is asked for. The Quo key and bot token go only into Vercel's locked
# settings; Val's computer gets only the helper's address and her drafts-only code.
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

KEYS="$(hidden 'the Quo key (1Password: Zingas Bridge > Bridge Secrets > QUO_API_KEY)')"
KEYS+=$'\n'"$(hidden 'the bot token (same note > APPROVALS_BOT_TOKEN)')"
KEYS+=$'\n'"$(hidden 'the Vercel token you just made')"
echo
printf 'Type your cell number (for the "a text is waiting" alert), then Return: '
IFS= read -r CELL
echo

printf '%s\n%s\n' "$KEYS" "$CELL" | python3 -I "$HERE/quo_setup.py" "$ORGO" "$COMPUTER"
unset KEYS CELL
echo
echo "You can close this tab."
