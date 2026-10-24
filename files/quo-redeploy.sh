#!/bin/bash
# ==========================================================================
# Zinga's Assistant: put the newest quo-bridge code online (nothing else changes)
# ==========================================================================
# Run on Gerrit's laptop. Make a Vercel token first (vercel.com > Account Settings > Tokens, your Pro team,
# expires in 1 day) and paste it into the hidden prompt. It is never shown and never saved on this laptop.
# No settings or keys change, and nobody gets a text. Delete the token in Vercel afterwards.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo >&2
echo "Paste the Vercel token you just made, then press Return. Nothing shows while you paste." >&2
printf '> ' >&2
IFS= read -rs TOKEN
echo >&2
TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
[ -n "$TOKEN" ] || { echo "Nothing pasted. Nothing was changed." >&2; exit 1; }

printf '%s\n' "$TOKEN" | python3 -I "$HERE/quo_redeploy.py"
unset TOKEN
echo
echo "You can close this tab and delete the Vercel token."
