# Setting up Val on her cloud computer

One part at a time. Gerrit says "done" after each; I do the rest.

| # | Part | Who | Time |
|---|---|---|---|
| 1 ✅ | Install Orgo's small helper tool on this laptop and sign in to Orgo in the browser. Lets me copy Val's files to her computer without uploading them anywhere else | Gerrit signs in, I install | 3 min |
| 2 ✅ | Copy Val's rules, personality and skills onto her computer (backing up what's there first) | Me | 5 min |
| 3 ✅ | Sign Val in to Nous Portal (her brain): open a link, enter a code | Gerrit | 3 min |
| 4 ✅ | Connect Val's Telegram chat | Gerrit | 5 min |
| 5 ✅ (Assistant code) | Read-only 1Password "service account" for the **Zingas Assistant** vault only. Paste its code into the hidden box (`files/save-op-token.sh`), never into chat. The **Zingas Bridge** one waits until mail-bridge is set up, so no unused code sits on Val's computer | Gerrit | 10 min |
| 6 ✅ | Turn on the healthchecks.io check-ins | Me, with Gerrit's link | 3 min |
| 7 ✅ | Test: close the laptop and text Val | Gerrit | 2 min |

**Status 2026-10-21: Val's setup is done.** All 7 parts work. The one piece left is the Zingas Bridge
code (part 5), which belongs with the mail-bridge step, not this setup.

**Done 2026-10-21:** Orgo helper installed in ~/.orgo-cli (signed in as gghuizinga23@gmail.com).
Val's files merged into the Orgo Hermes template with `files/install-on-orgo.py` (it keeps the template's
own config and adds ours on top). The old settings are backed up on Val's computer in
/root/.hermes/backups/pre-zingas-20261021-132025. Telegram was already connected by Orgo at launch.
Nous Portal signed in (gerrithuizinga@zingashome.com). Val's brain now runs through Nous, same model as
before (Claude Sonnet 5.5, `anthropic/claude-sonnet-5.5`), instead of Orgo's built-in AI credits.
The settings before this switch are in /root/.hermes/backups/config.before-nous.yaml. Test reply: "ok".
Telegram: Gerrit connected the bot chat on Orgo's site and sees it on the iPhone. Only 1 person is
allowed to talk to Val (home chat 8703312605). The laptop-off test (part 7) is the first real message.
1Password's tool (`op` 2.41.0) is installed on Val's computer from 1Password's own download site.
The 1Password list no longer names the Telegram or AI keys (Orgo holds the Telegram one; Nous needs none).
1Password: Val's read-only code (service account "Val", saved in Gerrit's own main vault) is on her
computer in ~/.hermes/.op.env (root only). It opens only Zingas Assistant. Val's 1Password list stays
off until the first key is in the note (part 6), so an empty note can't stall her.
healthchecks.io: check "Val" (every 10 min, 10 min grace). Its link is HEALTHCHECKS_PING_URL in
Assistant Secrets, now the only field Val's 1Password list reads (add the rest as their keys arrive).
`files/heartbeat.sh` runs under supervisord as `zingas-heartbeat`: pings while the gateway runs, reports
a failure if it stops. First check-in 2026-10-21 13:54 UTC.
Laptop-off test passed 2026-10-21: Gerrit closed the laptop, texted Val on Telegram, and she answered.

**Still to do for part 5:** the second read-only code, for Zingas Bridge, when mail-bridge (Gmail) is set up.

**Later (not today):** connect Gmail and Calendar through mail-bridge; the
approvals chat and customer texting (Quo approved 2026-10-21, ready to build); Plaud once it arrives.

**Rules that hold the whole way:**
- Nothing goes to GitHub or anywhere else; files go straight from this laptop to Val's computer.
- No passwords or keys in chat.
- Val can't send email or text customers yet.
