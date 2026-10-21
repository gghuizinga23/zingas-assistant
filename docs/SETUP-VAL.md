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

**Still to do for part 5:** the second read-only code, for Zingas Bridge. Gmail no longer needs it
(see below), so it waits for Quo texting.

## Gmail and Calendar (next, chosen 2026-10-21)

Val reads, searches and drafts email, and reads your calendar. She can **never** send, forward or
delete. **Why it's built this way:** Val can read every file on her computer, so the main Composio key
must never go there. I use it from this laptop to make a locked session that allows only the jobs
above. Val gets the session link plus a **limited key** that can only use that session: it can't make
a new session or reach any other tool.

| # | Part | Who | Time |
|---|---|---|---|
| G1 | In Composio (API Keys): save the **main** key in 1Password (**Zingas Bridge** vault, note **Bridge Secrets**, field **COMPOSIO_API_KEY**). Make a second key, **Val limited**, with only "Session tool execution: Write" (everything else None). Save it in **Zingas Assistant** vault, note **Assistant Secrets**, field **COMPOSIO_VAL_KEY**. Leave **Require API Key for MCP** ON. Never in chat | Gerrit | 10 min |
| G2 | Connect your zingashome.com Gmail and Calendar to Composio: open the link I give you and sign in to Google. If Google blocks it, Delisa allows Composio in Google Admin | Gerrit (Delisa if blocked) | 5 min |
| G3 | Paste the main key into a hidden box on this laptop. It makes the locked session (sandbox and raw-API access off) and sends only the session link to Val's computer. The main key is not saved anywhere | Gerrit pastes, I do the rest | 5 min |
| G4 | Safety tests with Val's limited key: sending an email to you, deleting one, and making a new session must all be refused. If any works, we stop and use a helper on Vercel instead | Me | 10 min |
| G5 | Turn it on for Val. Test: ask her on Telegram for your newest email and a draft reply. The draft shows in Gmail Drafts; nothing is sent | Gerrit | 3 min |

**G1: making the "Val limited" key** (Composio's "Create API key" window has a Read column and a
Write column, and **Read All** is ticked at the start):
1. Name: **Val limited**.
2. Untick **Read All**. Every box in the Read column clears.
3. Tick only one box: **Session tool execution**, Write column.
4. Scroll down to the end of the list and check that no other box is ticked (also Triggers, Webhooks,
   Observability, and the "Legacy" rows).
5. Click **Create**, copy the key, and save it in 1Password as COMPOSIO_VAL_KEY.

Tech notes: sessions replace Composio's old `mcp.create` (deprecated). Allowed tools:
GMAIL_FETCH_EMAILS, GMAIL_LIST_MESSAGES, GMAIL_LIST_THREADS, GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID,
GMAIL_FETCH_MESSAGE_BY_THREAD_ID, GMAIL_CREATE_EMAIL_DRAFT, GMAIL_LIST_DRAFTS, GMAIL_GET_DRAFT,
GMAIL_GET_ATTACHMENT, GOOGLECALENDAR_EVENTS_LIST, GOOGLECALENDAR_FIND_EVENT, GOOGLECALENDAR_EVENTS_GET,
GOOGLECALENDAR_LIST_CALENDARS, GOOGLECALENDAR_FREE_BUSY_QUERY. Google has no draft-only scope
(gmail.compose can send), so the lock must be Composio's. Hermes `tools: include` is not a lock
(it runs on Val's computer). Check at G3 whether sessions expire.

**Note for Quo later:** Quo's keys have the same problem (Val can read files on her computer).
Solve it the same way, or with a helper off her computer, before customer texting starts.

**Later (not today):** the
approvals chat and customer texting (Quo approved 2026-10-21, ready to build); Plaud once it arrives.

**Rules that hold the whole way:**
- Nothing goes to GitHub or anywhere else; files go straight from this laptop to Val's computer.
- No passwords or keys in chat.
- Val can't send email or text customers yet.
