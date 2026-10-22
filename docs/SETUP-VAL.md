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
| G2+G3 | Run the hidden box `files/gmail-setup.sh` and paste the **main** key. A Google sign-in opens twice (Gmail, then Calendar): sign in with zingashome.com and click Allow. If Google blocks it, Delisa allows Composio in Google Admin. Then it makes the locked session (no workbench, no raw API, no new connections, narrow Google scopes) and sends only the session link to Val's computer. The main key is not saved anywhere | Gerrit pastes and signs in, I do the rest | 10 min |
| G4 | Safety tests with Val's limited key: sending an email to you, deleting one, and making a new session must all be refused. If any works, we stop and use a helper on Vercel instead. **Done 2026-10-21 (Gmail only): `files/gmail-safety-check.sh` 16 of 16 passed.** Send, send-draft, reply, forward, delete, trash, new connection and workbench all came back "not found"; send through the multi-tool runner came back "Session Restriction"; Val's key got 403 for a new session, a direct send and the account list. Run it again after Calendar is added | Me | 10 min |
| G5 | ✅ **Done 2026-10-21.** Turn it on for Val. Test: ask her on Telegram for your newest email and a draft reply. The draft shows in Gmail Drafts; nothing is sent. Notes: Orgo's own "orgo" tool server (send email, calendar edits, Drive sharing, no tap) is turned off; Val searches all labels, not just the inbox; gear lines, thinking and in-between messages are off in Telegram | Gerrit | 3 min |

**G2 status 2026-10-21: Google said "This app is blocked"** (Gerrit's screenshot: "This app tried to
access sensitive info in your Google Account... Google blocked this access"). Google's admin help
(knowledge.workspace.google.com, "Control which apps access Google Workspace data") says this shows
when an app the admin hasn't trusted asks for a restricted service like Gmail. Delisa fixes it:
1. Google Admin console → **Security → Access and data control → API controls → Manage App Access**.
2. Find **Composio** in the list (Gerrit's blocked try should put it there; if not, add it by name).
3. Click **Change access**. Choose only Gerrit's org unit, or leave the top level for everyone.
4. Pick **Trusted** → **Next** → **Change access**.
Then run `files/gmail-setup.sh` again; it reuses what it already made.
**Delisa trusted Composio (Gerrit, 2026-10-21).** Next: G2+G3 again, then G4 and G5.

**G2 rerun 2026-10-21: Gmail connected; Calendar still "This app is blocked".** Composio's Calendar
sign-in shows up in Google as a separate app entry, or the trust Delisa set covers Gmail only. Delisa fixes it:
1. Same page: **Manage App Access**. Every **Composio** entry must be **Trusted**, not "Specific Google data"
   or "Limited". If there are two, trust both.
2. If Calendar's entry isn't listed: on Google's blocked page, Gerrit clicks **error details** and sends
   Delisa the **client ID**. Delisa clicks **Configure new app**, pastes that ID, and picks **Trusted**.
Meanwhile Gmail goes live alone: `GMAIL_ONLY=1 bash files/gmail-setup.sh`. Later, run
`bash files/gmail-setup.sh` once more to add Calendar. It skips Gmail and makes a new locked link.

**G1: making the "Val limited" key** (Composio's "Create API key" window has a Read column and a
Write column, and **Read All** is ticked at the start):
1. Name: **Val limited**.
2. Untick **Read All**. Every box in the Read column clears.
3. Tick only one box: **Session tool execution**, Write column.
4. Scroll down to the end of the list and check that no other box is ticked (also Triggers, Webhooks,
   Observability, and the "Legacy" rows).
5. Click **Create**, copy the key, and save it in 1Password as COMPOSIO_VAL_KEY.

**G1: making and saving the main key** (only this laptop's hidden box ever uses it):
1. In Composio's API Keys page, click **Create API Key**. Name: **Main (setup only)**.
2. Leave **Read All** ticked and also tick **Write All**. Click **Create** and copy the key.
3. In the 1Password app, open the **Zingas Bridge** vault (left side).
4. If there is a **Bridge Secrets** note, open it and click **Edit**. If there isn't one, click
   **+ New Item**, then **Secure Note**, and name it **Bridge Secrets**.
5. Click **+ add more**, then **Password**. Name the field **COMPOSIO_API_KEY** and paste the key as
   its value. Click **Save**.

Tech notes: sessions replace Composio's old `mcp.create` (deprecated). Allowed tools:
GMAIL_FETCH_EMAILS, GMAIL_LIST_MESSAGES, GMAIL_LIST_THREADS, GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID,
GMAIL_FETCH_MESSAGE_BY_THREAD_ID, GMAIL_CREATE_EMAIL_DRAFT, GMAIL_LIST_DRAFTS, GMAIL_GET_DRAFT,
GMAIL_GET_ATTACHMENT, GOOGLECALENDAR_EVENTS_LIST, GOOGLECALENDAR_FIND_EVENT, GOOGLECALENDAR_EVENTS_GET,
GOOGLECALENDAR_LIST_CALENDARS, GOOGLECALENDAR_FREE_BUSY_QUERY. Google has no draft-only scope
(gmail.compose can send), so the lock must be Composio's. Hermes `tools: include` is not a lock
(it runs on Val's computer). Check at G3 whether sessions expire.

## Quo texting (chosen 2026-10-21)

Customers text your Quo number. Val drafts each reply. **Only your tap sends a text.**
**Why it's built this way:** a Quo key can do everything in your Quo account (Quo's own docs:
"each key has full access to your workspace's API"; there are no limited keys). Val can read every
file on her computer, so the key never goes there. It lives in a small helper, **quo-bridge**, on
Vercel (Gerrit chose this 2026-10-21). Val gets a **drafts-only code**: she can hand the helper a
draft and pick up new customer texts, nothing else. Even if someone stole that code, the worst it
could do is put a draft in front of you.

| # | Part | Who | Time |
|---|---|---|---|
| Q1 | ✅ **Done (Gerrit, by 2026-10-21).** Move Vercel to **Pro** ($20 a month). The free plan is for personal use and only runs timed jobs once a day; the helper needs one every minute. Vercel → your team (top left) → **Settings → Billing → Upgrade to Pro**. This also covers the Estimator, which is a business tool on the free plan today | Gerrit | 5 min |
| Q2 | ✅ **Done (Gerrit, by 2026-10-21).** In Quo: (a) **Settings → Billing**: add API texting credits ($20 to start; about 1 cent a text). (b) **Workspace Settings → API → Generate API key**, name it `zingas-bridge`. Save it in 1Password, **Zingas Bridge** vault, note **Bridge Secrets**, field **QUO_API_KEY**. Never in chat | Gerrit | 10 min |
| Q3 | ✅ **Done (Gerrit, by 2026-10-21).** Make the **approvals bot** in Telegram: open **@BotFather** → `/newbot` → name **Val Approvals** → a username ending in `bot`. Save its token in **Bridge Secrets** as **APPROVALS_BOT_TOKEN**. Then open the new bot and press **Start** | Gerrit | 5 min |
| Q4 | ✅ **Done 2026-10-21.** quo-bridge and Val's pickup program are built. 109 tests pass with fake texts | Me | done |
| Q5 | Run a hidden box and paste the two keys. It puts them in Vercel's locked settings (never on Val's computer, and not saved on this laptop), connects Quo's "new text" alert to the helper, and gives Val her drafts-only code | Gerrit pastes, I do the rest | 10 min |
| Q6 | Safety tests: Val's code can't send; a fake "text from Quo" is refused; a 9pm send waits until 8am; money words never send alone; a customer who texts STOP is never texted again. (2 of the 10 live checks already pass on Val's computer: her drafting run reaches only a to-do tool, and an order hidden in a customer text only changes the draft) | Me | 15 min |
| Q7 | Real test: text the Quo number from your cell. Val's draft shows in **Val Approvals**. Tap **Approve**; the reply reaches your cell | Gerrit | 5 min |

**Q5 step by step (about 15 minutes, at your laptop):**
1. **Vercel token (for this run only):** open https://vercel.com/account/tokens. Name `quo-setup`.
   Scope: your **Pro team** → **All Projects**. Expiration: **1 day**. **Create**, then copy it.
2. **Supabase token (for this run only):** open https://supabase.com/dashboard/account/tokens →
   **Generate new token**, name `quo-setup`, copy it.
3. Tell me "ready". I open a hidden box. You paste, one at a time: the Quo key, the bot token
   (both from 1Password, Zingas Bridge → Bridge Secrets), the Vercel token, the Supabase token.
   Then type your cell number. Nothing shows while you paste, and nothing is saved on the laptop.
4. If it asks, open **Val Approvals** in Telegram and send it the word `hi`.
5. The box does the rest (about 5 minutes): a new free Supabase project, quo-bridge online on
   Vercel, Quo's new-text alert and the bot connected, the locks checked from outside, and Val's
   pickup program started. A "Val Approvals is connected" message lands in Telegram.
6. Delete both tokens (same two pages). They're not needed again.

**What quo-bridge does** (Q4):
- **New customer text:** Quo tells the helper; the helper checks it really came from Quo and saves it.
  A small program on Val's computer (no AI, no keys) asks the helper every 20 seconds for new texts
  and hands them to Val. Val's computer stays closed to the internet.
- **Val's draft** goes to the helper with her drafts-only code, then shows in **Val Approvals** with
  **Approve / Edit / Skip**. Only your Telegram account can press them.
- **On Approve** the helper runs the same safety rules as `quo-bridge/send_gate.py` (same tests),
  then sends through Quo. Every send is logged.
- **Every minute:** sends approved texts that waited for 8am, texts your cell when a draft sits
  10 minutes in work hours, marks drafts "missed" after 2 hours for the brief.
- **Auto-send stays off** at the start. Each kind earns it later (20 approvals in a row, no edits).
- Records go in a **new free Supabase project** just for Val's texts, not the dashboard's, so the
  helper can't reach dashboard data.

**Cost:** Vercel Pro $20 a month, Quo texts about 1 cent each, Supabase free.

**Later (not today):** Plaud once it arrives.

**Rules that hold the whole way:**
- Nothing goes to GitHub or anywhere else; files go straight from this laptop to Val's computer.
- No passwords or keys in chat.
- Val can't send email. She can't text customers until Q7, and then only after your tap.
