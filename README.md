# Zinga's Assistant

An always-on assistant for Gerrit. It reads work email and the Quo business
number, drafts every reply in Gerrit's voice, and waits for Gerrit's tap before anything
reaches a customer. It runs on an Orgo cloud computer, so it keeps working when
the laptop is closed. It is built on Nick's Stack (Hermes agent); see
`THIRD_PARTY_NOTICES.md`.

The full plan is in `docs/PLAN.md`. What Gerrit has to sign up for is in
`docs/PHASE-0-CHECKLIST.md`.

## How it fits together

- **Assistant bot (Telegram):** Gerrit chats with the assistant here all day.
  Gerrit can ask questions, send voice-note debriefs and get the morning and
  evening briefs.
- **Approvals bot (Telegram):** a second, separate bot owned by `quo-bridge`.
  Every customer text draft arrives here with Approve, Edit and Skip buttons.
  Only Gerrit's Telegram account can press them.
- **quo-bridge:** the only way a text reaches a customer. It checks every
  message in code before sending (`quo-bridge/send_gate.py`):
  - approved by Gerrit, or a type that has earned auto-send (then it waits 5
    minutes with a Stop button)
  - money, complaints, cancellations or "is this a real person?" in the
    customer's message always go to Gerrit
  - between 8am and 8pm in the customer's time zone
  - not on the do-not-contact list
  - no prices, discounts or dollar amounts in anything that sends by itself
  - never an appointment confirmation (corporate already sends those)
- **Email:** the assistant can read mail and create Gmail drafts. It cannot
  send email. Gerrit sends from the Gmail app.

## Folders

| Folder | What is in it |
|---|---|
| `files/` | What gets installed on the cloud computer: Hermes config, persona (`SOUL.md`), skills, setup scripts |
| `files/skills/zingas/` | Zinga's skills: voice, cadence, email triage and more |
| `quo-bridge/` | The customer-text gate and (next) the Quo webhook server |
| `docs/` | Plan and checklists |

This folder also holds the old Follow-Up prototype (`dashboard/`,
`salesforce/`, logs). Those files hold real customer data, so `.gitignore`
lets only the folders above into git. Keep it that way.

## Where files go on the cloud computer

| Repo file | Installed to |
|---|---|
| `files/config.yaml` | `/root/.hermes/config.yaml` |
| `files/hermes.env` | `/root/.hermes/.env` (then real keys come from 1Password) |
| `files/SOUL.md` | `/root/.hermes/SOUL.md` |
| `files/skills/zingas/` | `/root/.hermes/skills/zingas/` |
| `files/gateway-run.sh` | `/usr/local/bin/hermes-gateway-run.sh` (run by supervisord) |
| `files/onboard.sh` | `/usr/local/bin/zingas-assistant-onboard.sh` |
| `files/telegram-pair.py` | `/usr/local/bin/zingas-assistant-telegram-pair.py` |
| `files/op-enable.py` | `/usr/local/bin/zingas-assistant-op-enable` |
| `files/zingas_backup.py` | `/usr/local/bin/zingas-backup` (nightly backup, run by supervisord) |
| `files/zingas_followups.py` | `/usr/local/bin/zingas-followups` (F0 quote follow-ups, run by supervisord) |
| `files/followup_wording.py` | `/usr/local/lib/zingas/followup_wording.py` (the fixed follow-up wordings) |

## Tests

```bash
python3 -m unittest discover -s quo-bridge -v
```
