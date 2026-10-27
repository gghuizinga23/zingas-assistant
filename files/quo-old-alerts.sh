#!/bin/bash
# ==========================================================================
# Zinga's Assistant: remove Quo's old quo-bridge alerts (after quo-sent-setup.sh made the new ones)
# ==========================================================================
# Run on Gerrit's laptop. Paste the Quo key into the hidden prompt (1Password: Zingas Bridge > Bridge Secrets >
# QUO_API_KEY). It is never shown and never saved. For each of the three alerts (texts, calls, sent texts) the
# newest stays; older ones at quo-bridge's address are removed. Nobody gets a text. Nothing else changes.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo >&2
echo "Paste the Quo key (1Password: Zingas Bridge > Bridge Secrets > QUO_API_KEY), then press Return. Nothing shows while you paste." >&2
printf '> ' >&2
IFS= read -rs KEY
echo >&2
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
[ -n "$KEY" ] || { echo "Nothing pasted. Nothing was changed." >&2; exit 1; }

printf '%s\n' "$KEY" | python3 -I "$HERE/quo_sent_setup.py" --old-only
unset KEY
echo
echo "You can close this tab."
