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
**2026-10-22: still blocked.** Calendar's sign-in uses Google client ID
`126612815146-pkbs6vs1rqbvpknnim0hbt847cpp9ecu.apps.googleusercontent.com` (scopes: calendar.readonly,
userinfo.email). A reply to Delisa with this ID and the "Configure new app → Trusted" steps is in Gerrit's
Gmail Drafts. Once she says done: `bash files/gmail-setup.sh` again, then G4 with Calendar.
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
| Q5 | ✅ **Done 2026-10-22.** quo-bridge is online at https://zingas-quo-bridge.vercel.app. Quo's text and call/voicemail alerts and **Val Approvals** are connected; 7 of 7 lock checks passed from outside; Val's pickup program is RUNNING with only the helper's address and her drafts-only code. Records are in the **Zingas Assistant** Supabase organization (project "gghuizinga23's Project", reused because the free plan allows 2 projects). Fixes on the way: the laptop reaches Quo through curl (its Python is too old for Quo's servers); Supabase goes through the Supabase app signed in on this laptop, not a token (Gerrit's choice); the box refuses a cell number that is the Quo number | Gerrit pasted, I did the rest | done |
| Q6 | ✅ **Done 2026-10-22.** `files/quo-safety-check.sh` on Val's computer: 10 of 10 passed (Val's code can't run the timer or press Approve, a fake Quo alert and a wrong code are refused, a confirmation is blocked, no helper keys on Val's computer, her drafting run reaches only the to-do tool, an order hidden in a customer text only makes a draft). The rules (8am–8pm hold, money words, STOP, double taps) pass 95 of 95 quo-bridge tests | Me | done |
| Q7 | ✅ **Done 2026-10-22 (12:35 AM).** Gerrit texted the Quo number from his cell; Val's draft showed in **Val Approvals**; he tapped Approve, then 📤 Send now; the reply reached his cell. Fixes found on the way: Quo's firewall (Cloudflare, "error code: 1010") blocks Python's default name tag, so quo-bridge now calls Quo as `zingas-quo-bridge/1.0`; a held text (outside 8am–8pm) now has a 📤 Send now button that only Gerrit can tap; the bot answers typed messages with the buttons to use; a Quo refusal shows Quo's own words | Gerrit | done |

**Q5 step by step (to run it again; safe, it reuses what's there):**
1. **Vercel token (for this run only):** open https://vercel.com/account/tokens. Name `quo-setup`.
   Scope: your **Pro team** → **All Projects**. Expiration: **1 day**. **Create**, then copy it.
2. Supabase needs no token: the box uses the Supabase app signed in on this laptop
   (`supabase login` if it ever says it isn't signed in).
3. Run `files/quo-setup.sh`. Paste, one at a time: the Quo key, the bot token (both from
   1Password, Zingas Bridge → Bridge Secrets), the Vercel token. Then type your **personal** cell
   (not the Quo number). Nothing shows while you paste, and nothing is saved on the laptop.
4. If it asks, open **Val Approvals** in Telegram and send it the word `hi`.
5. Delete the Vercel token afterwards. It's not needed again.

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
- Records go in a **separate Supabase organization (Zingas Assistant)** just for Val's texts, not the
  dashboard's, so the helper can't reach dashboard data.

**Cost:** Vercel Pro $20 a month, Quo texts about 1 cent each, Supabase free.

## F0: quote follow-ups (built 2026-10-23)
Val finds every estimate you email a customer (your Sent mail, PDF attached) and the visit it belongs to
(the "Appt on ..." email from appointments@zingashome.com, which has the time and the phone). The clock
starts at the visit. **Calendar access is not needed.** You do no new work: she skips sold customers by
herself (a "Payment Link" email, a contract email to payments@, insidesalessupport@ or customersuccess@,
or the Gmail label Completed). When a customer writes back, their follow-ups pause; after 3 quiet days they
start again in Val's words from the conversation.

**Each weekday:** at 7:40 AM Val makes the day's list (Friday's has the weekend too). The 8:00 brief shows
it. At 8:01 **Val Approvals** posts one card: **Approve all**, or **Review one by one** (approve, edit or
remove each, or "No more follow-ups for them"). Approved ones send at their time, 8am to 8pm customer
time: a text from the Quo number and an email reply in the estimate's thread. Not approved by 8 PM:
nothing sends, and they come back the next morning.

**Status (2026-10-24): on.** F1 ran on Saturday 10/24: the follow-up tables are in quo-bridge's Supabase,
the new quo-bridge is online (follow-up doors locked: no code 401, Val's code can't run the timer), and
Val's program `zingas-followups` is live. The first list comes Monday 10/26: 7:40 AM list, 8:00 brief,
8:01 Approve all card. Nothing sends before Gerrit's tap.

| Step | What to do | Who | Time |
|---|---|---|---|
| F1 | ✅ **Done 2026-10-24.** **Vercel token (for this run only):** https://vercel.com/account/tokens, name `f0-setup`, scope your Pro team, expiry 1 day. Then run `bash files/f0-setup.sh` and paste the **Composio main key** (1Password: Zingas Bridge → Bridge Secrets → COMPOSIO_API_KEY) and the Vercel token. It checks the Gmail connection can read your Sent mail, adds the follow-up tables to Supabase, puts the key in quo-bridge's locked settings, puts the new quo-bridge online, checks the locks, and turns F0 on. Delete the Vercel token afterwards | Gerrit pastes, I do the rest | 5 min |
| F2 | The next weekday morning: read the follow-ups in the 8:00 brief and tap **Approve all** (or review them) in Val Approvals | Gerrit | 2 min |

**Why the Composio main key goes to quo-bridge:** Val can only draft email, on purpose. quo-bridge (on
Vercel, where Val has no access) sends only follow-ups you approved, only to an address that already got
an estimate from you, and logs each send. Val's computer never gets the main key.

## Plaud (device here 2026-10-23; built 2026-10-24)
The plan and what was built are in `docs/VAL-BRAIN.md`. Every visit recording becomes part of that customer's
one file (with every text, call and email), and every promise you make at a visit goes on your to-do list with
an alert, a few minutes after you stop recording. The recording replaces the truck debrief. Val reads all past
recordings (the last year) when P2 is done; old visits fill her memory only, with no to-dos or texts.

**Status (2026-10-24):** built and tested, **not on Val's computer yet**. Nothing changes for you until the
install step below.

| Step | What to do | Who | Time |
|---|---|---|---|
| P1 | **Now.** In the Plaud phone app: turn on **AutoFlow** (automatic transcripts) and speaker labels. Add product words to the custom vocabulary: PowerView, Silhouette, Pirouette, Duette, pergola, and others you say often. Then record every appointment: press record when the visit starts, stop when it ends. Don't connect Plaud to Zapier or anything else | Gerrit | 10 min |
| Install | **After your yes.** I run `bash files/install-plaud.sh` from the laptop. It saves a copy of every old file on Val's computer, puts the new programs on, installs the official Plaud program (read-only: it can list and read recordings, never delete or change them), and restarts Val's text and email programs. If it says Node.js is missing, I add that first (one more yes from you) | I do it | 5 min |
| P2 | **Plaud sign-in, on Val's own screen.** Open Val's computer in the Orgo dashboard (the screen view). I start `plaud login` there. A browser opens **on that screen** with the Plaud sign-in: sign in with your Plaud account and click **Authorize**. You have 2 minutes. No key to copy. (It must be the browser on Val's screen: the sign-in answers to Val's computer itself.) Then I run `zingas-plaud check`: it shows "Plaud sign-in: works" and today's recordings. **Done 2026-10-24.** If it is ever needed again: on Val's desktop the Plaud program opens a blank Chrome tab, so Claude opens the sign-in page itself through Chrome's DevTools port 9223 (the full address, URL-encoded) and brings it to the front; when Gerrit is already signed in to web.plaud.ai, only **Allow** is needed | You sign in, I do the rest | 5 min |
| P3 | **Test.** Record a 2-minute role-play at the time of a test appointment (made-up customer and phone), with one promise: "I'll drop off samples Friday." A few minutes after the phone app syncs: the to-do (🟢, due Friday) and its alert come in Telegram, and that evening's brief has the note to paste into Salesforce. Val makes an educated guess among that day's appointments ("Appt on" emails and your Google Calendar), so a visit you start early or late still finds its customer. A recording she is not sure about shows up once in the next morning brief with her best guess: answer it there ("yes" or "that one is the Smiths") or ignore it. A recording that is not a customer visit saves nothing | You record, I check | 10 min |

If the Plaud sign-in stops working later, Val tells you once (not at night), the morning brief says so, and
healthchecks.io sends its warning. Then do P2 again.

## Nightly backup (built 2026-10-23)
Every night at 2:30 AM, Val's computer packs her vault (customer notes, to-do list, voice), her settings,
skills, brief schedules, chat history and our programs into one file (about 3 MB today). It locks the file
with a password and uploads it to **Backblaze B2**. If her computer was off at 2:30, it runs when it is back on.
**Why it's built this way:** Val's B2 key can only **add** files. It can't read, list or delete them. So
nothing on her computer can spoil or read an old backup. Backblaze only sees locked files. Keys and passwords
are never in the backup (1Password has them). Getting a backup back needs a second, read-only key that
lives in the **Zingas Bridge** vault, which Val can't open.

**Status:** the program is installed and running on Val's computer (`zingas-backup`). It checks every hour
for the keys below, and the first backup runs within an hour after you save them. A full test on her real
files (pack, lock, unlock, compare) passed: 380 of 380 files came back the same, a wrong password was refused,
and no keys were in it. If a backup fails or is late (more than 30 hours), the next brief tells you.

| Step | What to do | Who | Time |
|---|---|---|---|
| B1 | **Sign up** at backblaze.com → **B2 Cloud Storage** → Sign up, with your zingashome.com email. Free for the first 10 GB, no card (Val's backups use far less). Save the login in 1Password, your own main vault | Gerrit | 5 min |
| B2 | **Make the bucket:** Buckets → **Create a Bucket**. Name: `zingas-val-backup` (if it's taken, add a few numbers). Files: **Private**. Default encryption: **Enable**. Object Lock: leave off. Then **Create** | Gerrit | 2 min |
| B3 | **Val's key (add only):** Application Keys → **Add a New Application Key**. Name `val-backup`. Bucket: `zingas-val-backup` only. Type of access: **Write Only**. Leave the rest empty. Click **Create**. It shows **keyID** and **applicationKey** once: in 1Password, **Zingas Assistant → Assistant Secrets**, add **B2_KEY_ID** (the keyID) and **B2_APP_KEY** (the applicationKey, as a password field). If there is no "Write Only" choice, stop and tell Claude | Gerrit | 5 min |
| B4 | **The lock password:** in the same note, add a password field **BACKUP_PASSPHRASE**. Use 1Password's generator (30 or more characters). Never change it: old backups only open with the password they were locked with | Gerrit | 2 min |
| B5 | **Restore key (read only):** back in Backblaze, add a second key. Name `restore`. Same bucket. Type of access: **Read Only**. Save it in **Zingas Bridge → Bridge Secrets** as **B2_RESTORE_KEY_ID** and **B2_RESTORE_KEY**. Not in Val's vault | Gerrit | 3 min |
| B6 | *Optional:* in healthchecks.io, project Val → **Add Check**. Name `Val nightly backup`, period **1 day**, grace **6 hours**. Copy its ping URL into Assistant Secrets as **BACKUP_PING_URL**. Then a missed backup also warns you by Telegram and email (the brief warns you anyway) | Gerrit | 3 min |
| B7 | **Restore test,** the morning after B3–B5: run `bash files/backup-restore.sh` and paste the 3 things it asks for. It gets the newest backup, unlocks it on Val's computer, compares every file with the live one, then deletes the test copy | Gerrit pastes, I read the result | 5 min |

**If Val's computer is ever lost:** start a new Orgo Hermes computer, then run
`APPLY=1 COMPUTER="<new computer name>" bash files/backup-restore.sh`. It puts every file back and restarts
Val's programs. Then the keys come back from 1Password: `files/save-op-token.sh` (1Password access) and
`files/quo-setup.sh` (Val's drafts-only code for quo-bridge). Telegram is connected again the way Orgo did it at launch.

**Cost:** free under 10 GB. Every backup is kept for now (about 1 GB a year at today's size).

## Activity log and watchdog (built 2026-10-26)
Why: on Sunday 10/25 at 5:34 AM Orgo's prepaid credits ran out and Orgo froze Val's computer. Monday's first
quote follow-up list never ran, and the only warning was a healthchecks.io email. Now:

- **Activity log.** A small program on Val's computer, `zingas-activity`, sends quo-bridge every minute the new
  lines from her programs' logs (follow-ups, backup, inbox, money, text pickup, Plaud; never her chat logs),
  "list made for <day>" when the follow-up list is made, "brief made" for each brief, and every 10 minutes a
  check-in saying which programs run. quo-bridge keeps it in its events table, next to its own rows (cards
  posted, texts sent). **To see it:** `bash files/val-log.sh` (today), `bash files/val-log.sh 3` (3 days),
  `bash files/val-log.sh 1 followups` (one program). Read only.
- **Watchdog.** quo-bridge's every-minute timer runs on Vercel, so it works when Val's computer is off. It texts
  your cell from the Quo number when: no check-in for 30 minutes ("Val is down", then "Val is back"); a program
  has been stopped 30+ minutes; or on a weekday no follow-up list by 8:10 AM. Texts wait for 7 AM to 10 PM. It
  says nothing until the first check-in arrives. The healthchecks.io email stays as a second warning.
- **Orgo credits:** Val costs about $1.20 a day (1 cent every 12 minutes). Turn on automatic top-up in Orgo if
  it offers one; `~/.orgo-cli/bin/orgo billing balance` shows what is left.

| Step | What to do | Who | Time |
|---|---|---|---|
| A1 | Say go to put branch `val-activity-log` on `main` (pushed to GitHub) | Gerrit says go, I do the rest | 1 min |
| A2 | **Put the new quo-bridge online.** Make a Vercel token (vercel.com → Account Settings → **Tokens**, your Pro team, expires in 1 day). I start `files/quo-redeploy.sh`; you paste the token into its hidden prompt. Code only: no settings or keys change, nobody gets a text. Then delete the token | Gerrit makes and pastes the token, I do the rest | 5 min |
| A3 | **Put the sender on Val's computer:** `bash files/install-activity-log.sh`. It copies one program and its settings, starts it, and shows its first lines; no other program restarts and no keys are copied | Gerrit says go (or runs it), I check | 2 min |
| A4 | Check: `bash files/val-log.sh` shows Val's check-ins and her program lines | Claude | 1 min |

## Val learns from your edits (built 2026-10-26)
Why: you asked that when you change a draft of Val's, she compares the two, learns what you did better and
writes the next one like it. Now:

- **What counts:** a text you edit (Telegram or the website), a follow-up text you edit, a Gmail draft of hers
  you change before sending, and a text you type yourself in the Quo app. Skipped drafts don't count.
- **Within 5 minutes** the program `zingas-voice` writes one short lesson ("Give a day, not soon"). A change
  that only fixes a fact (a day, a name) goes in the customer's file, not in the lessons. The next text draft
  gets the lessons plus the 3 to 5 past edits most like it; emails read the same lessons from the vault.
- **You text a customer yourself in Quo while Val's draft waits:** her draft stops (the card says "you texted
  them yourself"), so they never get two answers.
- **Sunday 6 PM:** one Telegram message: how many drafts went out with no change (this week and last), what she
  learned, and up to 5 lessons that keep coming back. Answer "rules 1 3" to make them permanent in VOICE.md.
  Nothing becomes permanent without your yes.
- **A wrong lesson:** tell Val in Telegram, or tap Remove on the website (Assistant > What Val learned, once
  that page is built). It stops at once.
- **Cost:** one small Val run per edited draft, cents a week.

| Step | What to do | Who | Time |
|---|---|---|---|
| V1 | Say go to put branch `voice-lessons` on `main` (pushed to GitHub) | Gerrit says go, I do the rest | 1 min |
| V2 | **Put the new quo-bridge online.** Make a Vercel token (vercel.com → Account Settings → **Tokens**, your Pro team, expires in 1 day). I start `files/quo-redeploy.sh` from a checkout of `main`; you paste the token into its hidden prompt. Code only, nobody gets a text | Gerrit makes and pastes the token, I do the rest | 5 min |
| V3 | **Quo tells quo-bridge about texts you send yourself:** I start `files/quo-sent-setup.sh`; you paste the Quo key (1Password: Zingas Bridge → Bridge Secrets → `QUO_API_KEY`) and the same Vercel token. It makes Quo's three alerts again (new texts, calls, and now sent texts), saves their keys in Vercel, puts quo-bridge online, then removes the old alerts. Nobody gets a text. Then delete the token. **2026-10-26 run:** the new alerts and keys went in and quo-bridge went online, but removing the old alerts failed (it used Quo's old v1 address; fixed). `files/quo-old-alerts.sh` (Quo key only) removes them: for each of the three names the newest alert stays | Gerrit pastes the two keys, I do the rest | 5 min |
| V4 | **Put zingas-voice on Val's computer:** `bash files/install-voice.sh`. It backs up the old files, copies the new ones, restarts the text pickup, inbox and follow-ups programs and starts zingas-voice | Gerrit says go (or runs it), I check | 3 min |
| V5 | Learn from the edits already saved (`zingas-voice backfill`), read the lessons, check a draft prompt and print Sunday's message without sending it (`zingas-voice weekly --dry`) | Claude | 10 min |

## Missed-call text-back (built 2026-10-26, plan F2)
Why: a missed call is a lead lost that day. Now:

- **A missed call or a voicemail** on the Quo number becomes a "Sorry I missed you" card in Val Approvals, as
  well as the "Call back" task it already made. Nothing sends until you tap Approve.
- **The call-back time comes from your calendar:** your next free 15 minutes, at least 20 minutes away, Monday to
  Saturday 9 AM to 7 PM, never in a visit, the 30 minutes before it (driving) or the 15 after. The "Call back"
  task says the time the text promises. If the calendar doesn't answer, the text says "as soon as I can".
  (Those hours are a guess: tell Claude yours and they change in `files/missed_call.py`.)
- **A call after 8 PM:** the text waits for 8 AM like every text, and its time is counted from that morning.
- **One text per person:** a second call while the first card waits gets no second card. If they texted too,
  the reply to their text covers it.
- **You call them back first** (from the Quo number): the card stops ("you called them back"), so they don't
  get "I'll call you back" after the call.
- A voicemail's words go through the same checks as a text: money, upset or cancelling shows ⚠️ on the card.
- Do-not-contact numbers get no text, only the task.
- **Cost:** one small Val run per missed call.

| Step | What to do | Who | Time |
|---|---|---|---|
| T1 | Say go to put branch `missed-call-textback` on `main` (pushed to GitHub) | Gerrit says go, I do the rest | 1 min |
| T2 | **Put the new quo-bridge online.** Make a Vercel token (vercel.com → Account Settings → **Tokens**, your Pro team, expires in 1 day). I start `files/quo-redeploy.sh` from a checkout of `main`; you paste the token into its hidden prompt. Then delete the token. Code only, nobody gets a text | Gerrit makes and pastes the token, I do the rest | 5 min |
| T3 | **Put the text-back on Val's computer:** `bash files/install-missed-call.sh` (after T2). It backs up the old files, copies the new ones and restarts the text pickup | Gerrit says go, I run it and check | 3 min |
| T4 | Check: call the Quo number from your cell and hang up. Within a minute a card says "[Missed call. No voicemail.]" with a call-back time that fits your calendar. Skip it (or call yourself back and see the card stop) | Gerrit makes the call, I check | 3 min |

## Val keeps the Follow-Up sheet filled in (built 2026-10-26, Follow-Up plan Phase 3, first part)
Why: on the new Follow-Up page "how warm", "waiting on" and "next step" were empty for every customer, and
"Your calls" was picked by a plain rule. Now the program `zingas-sheet` (`files/zingas_sheet.py`) does it:

- **Every 10 minutes**, for each of your open quotes: every new text, call, voicemail, email and visit in the
  customer's file goes on the sheet as a touch, and "last contact" moves forward. No AI for that part.
- **What Val judges from:** the sheet, her customer file, and each customer's Salesforce record (visits, results
  and your follow-up note from each visit; never prices), read once for each customer she judges.
- **Customers with news** (and, the first time, everyone) get one short Val run per 8 customers: how warm
  (hot, warm, cold), what we wait on, the next step (it shows on "Your calls" as the reason), a follow-up date
  only when you or the customer named a day, and one note line only when something new happened (at most one
  Val note a customer a day).
- **The rep always wins**, as on the sheet today: a part you set, "I've got this", a pause, Sold or Lost is never
  changed. Undo works on all of it.
- **"Tell Val what happened"** on a customer: she looks again within 2 minutes and turns your words into the next
  step and date (no note: yours is already there).
- It contacts **no customer**, and writes no price (amounts become "[amount]").
- **The first fill takes about an hour,** a little every 10 minutes (the newest 5 contacts per customer), because
  Val's website key is shared by all her programs and allows 120 calls per 10 minutes.
- **Cost:** about 5 small runs the first time for your 35 customers, then one run per batch with news.

| Step | What to do | Who | Time |
|---|---|---|---|
| S1 | Say go to put branch `missed-call-textback` (it has this too) on `main` | Gerrit says go, I do the rest | 1 min |
| S2 | **Look first:** `START=0 bash files/install-sheet.sh` copies the files without starting anything and prints what Val would write for up to 8 customers (`zingas-sheet preview`, writes nothing). I show you the list | Gerrit says go, I run it | 5 min |
| S3 | **Start it:** `bash files/install-sheet.sh`. It backs up the old files, copies the new ones and starts zingas-sheet | Gerrit says go, I run it and check | 3 min |
| S4 | Check on the website: Follow-Up → Today shows "how warm" and a next step on your customers, each with "Set by Val · Undo" | Claude | 5 min |

## Money tracker (planned 2026-10-23; cost count built 2026-10-24)
Val keeps a running total of everything you pay for: her own costs and your own AI and tool sign-ups. She
counts her use every hour, reads the receipts herself, and checks her numbers against them each month. You
get a money block in the Monday brief, a statement each month, alerts (for example "Nous credits stop in
4 days"), and her ROI. It all shows on the website's **Assistant > Cost** tab, for you only. The plan is in
`docs/PLAN.md`, "Money: costs and ROI".

**Built 2026-10-24 (step C1). Both are on since 2026-10-24: Val's counter (M1) and quo-bridge's text count (M3):**
- **Val's counter** (`zingas-money`, `files/zingas_money.py`) runs on her computer and, about every hour, sends
  the website one count: AI use (from the token counts Hermes already keeps), your fixed plans, Backblaze,
  how much Nous use is left and for how many days, and follow-ups sent. It uses the website key Val already
  has in 1Password (`ASSISTANT_API_TOKEN`), so **no new code is needed** (the old step "one new code for the
  Assistant tab" is gone).
- **quo-bridge** sends its own count of the texts it sent this month, once an hour, with the key it already
  has (`ZINGAS_OS_TOKEN`).
- A test run on Val's real numbers (nothing sent) on 2026-10-24: Nous $20 so far (the plan; her use, about
  $4, is still inside the $22 included), a pace of about $41 a month, $17.68 of included use left, which lasts
  about 23 days at this pace. The website's check took the count.

**Your plans and amounts stay in the vault, never in git** (this repo is public). The list is
`money/subscriptions.json` in Val's vault. Val keeps it up to date from receipts. A line is marked "receipt"
when this month's receipt is in it, otherwise "estimate". Example of the shape (made-up numbers):

```json
{"subscriptions": [
  {"id": "orgo", "name": "Orgo", "cost": 29, "cycle": "month", "nextRenewal": "2026-11-21",
   "receipts": [{"date": "2026-10-21", "amount": 29}]},
  {"id": "nous", "name": "Nous Portal", "cost": 20, "cycle": "month", "plan": "plus"},
  {"id": "chatgpt", "name": "ChatGPT", "cost": 20, "cycle": "month", "personal": true, "lastUsed": "2026-10-20"}
]}
```

`cycle` is `month`, `year` or `once`. A `once` row is a one-time charge, like a sign-up fee or a top-up of
Quo's prepaid text credits: it counts only in the month of its receipt and is not on the plans list. Texts
are paid from those credits, so the top-up (`quo-credits`) is the cash and quo-bridge's texts line adds $0.
`personal: true` marks your own sign-ups (only admins see them). The Nous line already includes the $20 plan,
so it is never counted twice. If you ever buy Nous credits, Val writes `money/credits.json`
(`{"left": 25, "asOf": "2026-11-02T09:00:00-05:00"}`), and the "days left" then counts them too.

Receipts that come to your work Gmail need nothing. Receipts that come to your personal Gmail reach Val
only through the filter in C1. She never reads anything else there.

| Step | What to do | Who | Time |
|---|---|---|---|
| M1 | ✅ **Done 2026-10-24 (1:23 PM), with Gerrit's go.** The installer ran from `main` 020249e: `zingas-money` is RUNNING on Val's computer, the website took her first count, and Assistant > Cost shows her numbers. Old files kept in `/root/.hermes/backups/pre-zingas-money-20261024-132324`. To run it again: `files/install-zingas-money.sh` from this laptop (the Orgo helper is already signed in). It copies the counter to Val's computer, starts it, sends the first count, and tells us whether the website took it. Then the Cost tab shows Val's numbers | Gerrit says go, I do the rest | 2 min |
| M2 | ✅ **Done 2026-10-24 (Claude, no step for Gerrit).** Checked against work Gmail: the 4 Quo receipts match; added the Nous receipt ($20, Oct 21), **1Password** ($35.88 a year after the free trial ends Nov 4; check that receipt) and **Vercel Pro** ($20 a month, Q1). Orgo, Plaud and Vercel have no receipt in work Gmail (they come with C1's forwarding), so they stay estimates. Was: **Starting list of your plans.** I write `money/subscriptions.json` in Val's vault from the plans in `docs/PHASE-0-CHECKLIST.md` (Orgo, Nous, Quo, Plaud and others). Look at it once on the Cost tab and tell me anything that is wrong. After that Val keeps it up to date from receipts | I write it, Gerrit checks | 3 min |
| M3 | ✅ **Already done by 2026-10-24 (no token needed).** The live quo-bridge sends its text count: the Cost tab shows "Quo texts (… so far, paid from prepaid credits)", the wording from bbfe740, and quo-bridge hasn't changed since. If quo-bridge changes again: **Put the new quo-bridge online,** so it sends its text count. Make a Vercel token (vercel.com → Account Settings → **Tokens**, your Pro team, expires in 1 day). I start `files/quo-redeploy.sh`; you paste the token into its hidden prompt. It uploads the code only: no settings or keys change, and nobody gets a text. Then delete the token in Vercel | Gerrit makes and pastes the token, I do the rest | 5 min |
| C1 | **Forward receipts from personal Gmail.** In personal Gmail on a computer: Settings → **Forwarding and POP/IMAP** → **Add a forwarding address** → your zingashome.com address. Gmail sends a code to your work Gmail: confirm it. Then make a filter with the search text I give you (the billing senders, for example Orgo, Nous, Plaud, Claude, ChatGPT) → **Forward it to** your work address. In work Gmail, the label **Val Receipts** catches them. Don't turn on forwarding for all mail | Gerrit | 5 min |
| C3 | *Optional:* read the first monthly statement. Tell Val only if something is wrong (a service that isn't yours, a price that is off) | Gerrit | 2 min |

**If the Cost tab says "over 3 hours old":** Val's counter or quo-bridge stopped sending. On Val's computer,
`zingas-money status` shows the last error (for example the website's reason for refusing a count).

**Cost:** nothing new. It runs on Val's computer and the website you already pay for.

**Rules that hold the whole way:**
- Nothing goes to GitHub or anywhere else; files go straight from this laptop to Val's computer.
- No passwords or keys in chat.
- Val can't send email. She texts customers only after your tap (Approve, or Send now on a text held outside 8am–8pm). Follow-up emails are sent by quo-bridge, only after your tap.
