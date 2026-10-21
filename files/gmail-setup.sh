#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Gmail parts G2 + G3 (connect Google, make Val's locked link)
# ==========================================================================
# Run on Gerrit's laptop. The main Composio key is typed into a hidden prompt and
# handed to files/gmail_setup.py on stdin. It is never shown, never saved, and
# never sent to Val's computer: only the locked session's link goes there.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

echo
echo "Paste the MAIN Composio key (1Password: Zingas Bridge > Bridge Secrets >"
echo "COMPOSIO_API_KEY), then press Return. Nothing shows while you paste."
printf '> '
IFS= read -rs KEY
echo
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
[ -n "$KEY" ] || { echo "Nothing pasted. Nothing was changed."; exit 1; }

printf '%s\n' "$KEY" | python3 -I "$HERE/gmail_setup.py" "$ORGO" "$COMPUTER"
unset KEY
echo
echo "You can close this tab."
