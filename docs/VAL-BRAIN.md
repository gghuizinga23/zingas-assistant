# Val's brain: Plaud visits, one file per customer, and what comes next

**Status:** plan approved by Gerrit 2026-10-23. **Parts 1–4 built 2026-10-24** (branch `claude/plaud-memory-c55472`,
all tests pass). **Not on Val's computer yet:** it goes on with `files/install-plaud.sh` after Gerrit's yes, then
Gerrit's steps P2 and P3 (`docs/SETUP-VAL.md`). What was built, and where it differs from the plan below, is in
"Built 2026-10-24" at the end. Part 5 (Val's brain, B1–B5) is the next step.

## Context
Gerrit has his Plaud and the Unlimited plan. Goals (2026-10-23):
1. Every appointment is recorded, transcribed and filed under that customer automatically.
2. Each customer has **one file that holds everything**: every visit, text, call, voicemail and email.
   Whenever Val deals with that customer's phone number or email, she reads it first, so her replies
   come from the full story and sound like a person who remembers, not a robot.
3. When Gerrit promises a customer something at the visit that Val can't do herself, it goes on his
   to-do list right away. Every new to-do sends Gerrit a notification and the list is re-sorted,
   highest priority at the top, every time.

Gerrit's choices: keep the **full transcript plus key facts**; the recording **replaces the 60-second
truck debrief**; build **right after F0**; **Gerrit first**, reps in Phase 5. The only habit: press
record when the visit starts, stop when it ends (consent is already collected at every appointment).

## What Gerrit does now (before the build)
1. In the Plaud app: turn on **AutoFlow** (automatic transcripts) and speaker labels. Add product words to
   the custom vocabulary (PowerView, Silhouette, Pirouette, pergola, and so on).
2. Record every appointment from today on. Val reads all past recordings on her first run.
3. Don't connect Plaud to Zapier or anything else.

## Part 1: the customer file (one place for everything)
Today the note `customers/<ProspectID>.md` holds facts only. Emails never touch it, texts only read it,
and nothing keeps a history. New layout in the vault, keyed by Salesforce Prospect ID:
- `customers/<ProspectID>.md` (**profile**, kept as is so `find_customer_note()` still works): names and who
  decides, phones, emails, address, products and rooms, likes, worries, objection, timing, personal details,
  and two new blocks at the top: **Where the sale is** and **Last 5 contacts** (one line each).
- `history/<ProspectID>.md` (**timeline**, new, append-only): one dated entry per contact, newest last.
  Each entry: date and time, channel, who spoke, a 1–3 line summary, and a pointer to the full text.
  - Visit: Plaud summary + link to the full transcript `visits/<ProspectID>/<date>-<plaudid>.md`.
  - Text in and out: the words (short), from `quo_pickup.py` and the approved sends.
  - Call / voicemail: Quo's voicemail transcript or answered-call summary (quo-bridge already stores these).
  - Email in and out: subject + summary, from `zingas_inbox.py` and Gmail Sent.
- **New shared module `files/zingas_customer.py`**, used by all three pickups:
  - `resolve(phone=, email=)` → Prospect ID (phone first, then email, new; then calendar; never name alone).
  - `log(pid, channel, when, summary, ref)` → appends to the timeline, refreshes "Last 5 contacts".
  - `context(pid)` → profile + the last 15 timeline entries + the newest visit summary, sized for a prompt.
  - Unmatched contacts log to their `unmatched-<phone>` stub, and the history moves over when matched.
- `quo_pickup.py` and `zingas_inbox.py` call `context()` before Val drafts or judges, instead of the raw
  first 3,000 characters of the note. In Telegram, Val opens the full timeline and transcripts through her
  vault tool when Gerrit asks ("What color did Mrs. Smith like?").
- Not covered: calls and texts on Gerrit's personal cell (by the plan, it is not read live).

## Part 2: Plaud visits
```
Plaud (AutoFlow) ──► Plaud cloud ◄── plaud CLI ── zingas-plaud (plain code, Val's computer, every 2 min)
                                                      1. new recording with a finished transcript?
                                                      2. save the transcript: vault/visits/...
                                                      3. match it to an appointment → Prospect ID
                                                      4. Val reads it (no-tools run) → facts JSON
                                                      5. code writes profile, timeline, to-dos, draft, brief
```
**Connection: the official Plaud CLI** (`@plaud-ai/cli`) on Val's Orgo computer. No Zapier, no webhook:
Val's computer only reaches out, like the Quo poller. One-time `plaud login` (Gerrit opens the printed link
and signs in). The CLI can list and read recordings, with no delete or edit commands. Used:
`plaud recent --days N`, `plaud file <id>`, `plaud transcript <id> -o`, `plaud summary <id> -o`.
- **Check first:** the CLI has no documented JSON output. If its text is hard to read reliably, use the
  official MCP server (`@plaud-ai/mcp`, `get_transcript` with speaker labels) instead.

**Matching a recording to a customer** (customer-memory rules):
1. Recording start time against Gerrit's Google Calendar appointments (each has PROSPECT and PHONE). Only one
   appointment fits → match.
2. A phone or email said in the transcript → match against profiles.
3. A name or address said in the transcript → suggestion only.
4. Not sure: one line in the **morning brief**, inside the approval Gerrit already does ("The 2:10 PM
   recording: Smith or Jones?"). No new Telegram question.
- ~~Depends on Calendar access.~~ **Built 2026-10-24 without waiting on it:** the time and phone come first
  from the "Appt on ..." emails that F0 already reads (`followups/state.json`), so this works today. When no
  email fits, Val looks at Gerrit's Google Calendar through the website (`/api/assistant/appointments`, once
  Gerrit connects it): an event whose time fits, with a phone (and a PROSPECT id, if there is one) in its
  title, place or note.

**What Val makes from each visit.** Val reads the **entire transcript** (not just Plaud's summary) and pulls
out every action item herself. One `hermes chat --oneshot -t todo` run, as in `quo_pickup.py`: the
transcript is data inside tags, never instructions; the program, not Val, writes the files. A 90-minute
visit is about 20,000 words, which fits in one run. Output:
- the visit file, a timeline entry, and new tagged facts in the profile (`(recording 10/23/26)`); two
  sources disagree → keep both and flag it in the brief
- **every promise Gerrit made** that Val can't do herself ("I'll bring fabric samples Friday", "I'll ask the
  office about install dates") → a to-do task with who, what and the due date he said (see Part 3).
  Things Val can do (a thank-you text, sending the quote link) become drafts on the normal Approve card.
- the debrief outputs: the follow-up note in the house format (`10/23/26 - ...; GH`), the follow-up date and
  the spouse name, in the evening brief for Gerrit to paste into Salesforce (write access is on hold)
- a same-day "great to meet you" draft on the normal approval card
- Drafts never quote the recording or use a detail that feels like surveillance (zingas-voice rule).

**"Immediately":** Plaud can't send anything during the visit. The NotePin syncs to the Plaud phone app
when Gerrit stops recording, and AutoFlow transcribes in a few minutes. Val checks every 2 minutes, so the
to-dos arrive a few minutes after the visit ends, usually while Gerrit is still in the driveway.

## Part 3: to-do alerts and order
Most of this already works in `files/zingas_todo.py`: `sort_items()` puts Now 🔴 → Today 🟡 → This week 🟢 →
Later ⚪ from top to bottom, then the oldest unanswered message, then the nearest due date; `renumber()`
runs on every change; `announce()` sends Gerrit the new task plus the whole re-sorted list.
Gaps to close:
- `announce()` stays silent after 8pm and on weekends (SOUL quiet hours). Evening visits often end after 8pm.
  **Gerrit's choice: every new to-do pings him right away, any hour, any day.** Remove the quiet-hours check
  from `announce()` only; all other Val messages keep quiet hours. Update SOUL.md and the todo-list skill to
  say so, and the test in `test_zingas_todo.py` that expects silence at night.
- A task Val adds from Telegram (`zingas-todo add`) shows only in her reply, with no separate alert. Make the
  CLI `add` call `announce()` too, so every path alerts the same way.
- Promises from visits get priority from the due date: today or tomorrow → 🟡 Today; this week → 🟢; no date
  → 🟡 Today with "you promised this at the visit".
- Every task added from a visit links to the customer, and its timeline entry shows "promised".

## Part 4: more context so Val sounds human
Each idea uses data Val can read herself (no new work for Gerrit). **Gerrit's pick: 1–5 go in this build**
as fields in the profile that Val fills from visits, texts and emails, and that `context()` hands to every
draft. 6–10 stay as ideas for later (6 and 7 need Calendar and office emails; 9 needs Gerrit's facts once).
1. **How each customer talks:** short or long, emojis or not, text or email, the name they go by, both
   spouses' names, the best time they answer. Val mirrors it in drafts. Comes from the timeline.
2. **Life events with dates:** "daughter's wedding in June", "moving in March", "back from Florida the
   15th". Val brings it up at the right time ("How was the wedding?"). Comes from visits and texts.
3. **The house:** rooms, which windows get hot afternoon sun, pets or kids (cordless matters), the problem
   they want solved. Lets follow-ups talk about their problem, not the product.
4. **What Gerrit already said:** promises, answers he gave and how warm the relationship is, so Val never
   repeats herself, contradicts him, or sounds more formal than he was in person.
5. **Mood over time:** warm, cooling, gone quiet, unhappy. Val backs off after silence and slows down
   when someone is upset, the way a person would.
6. **Where their order is:** order and install status from office emails, so "When is my install?" gets a
   real answer instead of "let me check".
7. **Gerrit's day:** his calendar (at an appointment until 3, driving), so a reply sounds like him ("I'm
   with a customer right now, I'll call you after 4").
8. **Local touch:** their town's weather this week and the teams they follow (SOUL already mentions
   Indiana teams). Used now and then, never forced.
9. **Product and company facts:** Hunter Douglas product notes, typical lead times, warranty, care, office
   hours. Specific answers sound human; vague ones sound like a bot. No prices.
10. **Gerrit's past replies to similar customers:** already planned (voice examples); make them match the
    sale stage and the customer type.

## Part 5 (next step, after this build): building out Val's brain
Its own step after Parts 1–4 ship. During the build, write it up as `docs/VAL-BRAIN.md` and add it to the
build order in `docs/PLAN.md`. Today Hermes's own memory holds only 2,200 characters, so everything Val
knows about customers and the business must live in the vault, wired as below.

### How it's wired
**Five shelves** (all plain files in the vault, so Gerrit can read them and the nightly backup covers them):
| Shelf | What's on it | Where |
|---|---|---|
| Customers | profile, timeline, visit transcripts (Parts 1–2) | `customers/`, `history/`, `visits/` |
| Gerrit | how he works, his week, his goals, his standing rules, the people he works with | `gerrit/` (+ existing `MEMORY.md`, `VOICE.md`) |
| Business | products, processes, lead times, warranty, office hours, who does what | `knowledge/` |
| Playbook | what works: objection answers, follow-ups that got replies, what Gerrit does at each sale stage | `playbook/` |
| World | holidays, local events, weather, team schedules | `world/` |

**One way in (write path):** every new thing (visit, text, call, email, Estimator event, Salesforce export,
office email) goes through `zingas_customer.log()`: match the person, add a timeline entry, then pull out
facts into the profile. Nothing writes the shelves any other way.

**One way out (read path, the "briefing packet"):** before Val drafts, judges or answers about a customer,
`context(pid, purpose)` builds one packet, about 6,000 words at most:
1. **The story so far:** a short running summary of this customer, refreshed after every contact
2. the profile facts, each with its source and date
3. the last 15 contacts
4. **search hits:** transcript and email passages that match what the customer just asked about
5. open loops: what Gerrit promised, what the customer said they'd do
6. Gerrit's day (calendar) and the matching playbook entry and business facts

**Search:** one SQLite full-text index (`vault/index/brain.db`, built into Python, no new service) over
timelines, transcripts, knowledge and playbook. `zingas-brain search "fabric color" --customer <pid>` lets
Val dig from Telegram. Updated each time `log()` runs.

**Think before writing:** each draft run first writes a short hidden "read of the situation" (sale stage,
what they want, the goal of this message, what not to say), then the draft. The read goes in the timeline,
so the next draft stays consistent.

**Nightly review (2 am, plain code + one Val run per customer touched that day):** refresh "the story so
far", merge new facts, retire facts that went stale ("moving in March" after March), find open loops and
overdue promises (→ to-do), flag facts that disagree. **Weekly:** compare outcomes (Salesforce Result) with
what was said and sent, and add lessons to the playbook.

**Self-check before the Approve card:** a second quick pass checks the draft against the file: wrong name,
contradicts something Gerrit said, asks a question already answered, uses a detail that feels like
surveillance, promises something Gerrit can't do, money words. Problems show as a line on the card.

**Fact hygiene:** every fact has a source, a date and how sure Val is. Time-bound facts get an end date.
Two sources disagree → keep both, flag it.

### More context to add (ideas 11–32, on top of 1–10 in Part 4)
All come from data Val reads herself; ★ = needs Gerrit once (a short list or a link), never per customer.

**About the customer**
11. **Lead source:** home show, website, referral, past customer. A referral gets "Your neighbor the Lees
    said great things" warmth; a web lead gets more explaining. (Salesforce)
12. **Past purchases:** what they already own from Zinga's and when it was installed, so a repeat customer
    is treated like one. (Salesforce, Gmail **Completed** label)
13. **Who decides what:** who researches, who cares about cost, who must be home, who to text. (visits)
14. **Competitors in the picture:** who else quoted and what the customer said about them. (visits, texts)
15. **Budget signals in words:** "we want to do it in stages", "financing?". Never numbers in texts. (visits)
16. **Proposal activity:** opened 3 times, looked at option B, forwarded it. (Estimator, F8)
17. **Every question they asked**, answered or not, so nothing slips and nothing gets asked twice.
18. **Open loops on their side:** "we'll talk it over this weekend" → Val waits until Monday, then nudges.
19. **Contact rules:** "text my wife instead", "not before 10", "email only". (texts, visits)
20. **Shared moments:** jokes, stories and small talk from the visit that Gerrit can call back to. (visits)
21. **Service history:** problems, repairs and warranty claims after install. (office emails)
22. **Important dates:** purchase and install anniversaries, a move-in date, a planned party. (all)

**About the home and neighborhood**
23. **Home details from public records:** year built, style, square feet (helps with "older homes like
    yours"). Public data only, used quietly, never quoted.
24. **Nearby jobs and HOA:** other Zinga's installs close by, HOA rules on outside products. (F5, Salesforce)

**About Gerrit and the business**
25. **Gerrit's week and load:** how many visits today, when he's free, so Val bundles asks and times
    replies like he would. (Calendar)
26. **Gerrit's goals:** this month's number vs goal, so hot quotes rise on the to-do list. (F7 dashboard)
27. **People directory ★:** office staff, installers, managers: names and who handles what, so Val says
    "Delisa in our office will call you" and routes things right.
28. **Order pipeline:** measure, order, ship and install dates per job. (office emails, Salesforce)
29. **Stage playbook:** what Gerrit does at each sale stage, learned from his own past follow-ups. (F1)
30. **Winning answers:** objections and the answers that came before a sale, from recordings. (F6, F11)

**About the world**
31. **Holidays and local events:** no texts on Thanksgiving, Indy 500 weekend small talk, school
    starting. (a yearly calendar file)
32. **Season and weather:** first hot week, storms, early sunsets; outdoor products in spring. (F9 feed)

### Brain build order (after Parts 1–4)
| Step | What | Why first |
|---|---|---|
| B1 | Search index + "the story so far" + think-before-writing + self-check | Makes every draft clearer with data Val already has |
| B2 | Nightly and weekly review, fact hygiene, open loops (11–22 from visits, texts, emails) | Keeps the files clean as they grow |
| B3 | Gerrit and Business shelves: people directory ★ (27), Gerrit's week (25), holidays (31) | Small, one-time; needs Calendar |
| B4 | Salesforce and Estimator facts: 11, 12, 16, 24, 28 | Needs the F1 customer lookup and Estimator Phase 1.5 |
| B5 | Playbook: 29, 30, then goals (26), weather (32), public records (23) | Needs weeks of recordings and outcomes |

Each step ends with a check: 10 drafts before and after, and Gerrit's unedited-draft rate should go up.

## Files to add or change
- **New** `files/zingas_customer.py` + `files/test_zingas_customer.py` (resolve, log, context, unmatched move).
- **New** `files/plaud_pickup.py` (`zingas-plaud run | check | backfill`), `files/zingas-plaud.supervisor.conf`,
  `files/test_plaud_pickup.py`. Reuse from `quo_pickup.py`: the oneshot Val call and the data-not-instructions
  prompt pattern; from `zingas_todo.py`: `apply_judgement()`, `announce()`.
- `files/quo_pickup.py`, `files/zingas_inbox.py`: log every contact, draft from `context()`.
- `quo-bridge/`: hand approved outgoing texts back to Val's computer so they get logged (check whether
  `/api/val/updates` already returns them).
- `files/zingas_todo.py`: CLI `add` announces; `announce()` no longer waits for quiet hours.
- `files/install-on-orgo.py`: install the Plaud CLI and the new program.
- Skills: `customer-memory` (profile + timeline + visits), `briefs` (unmatched recordings, notes to paste),
  `todo-list` (promises from visits).
- `files/zingas_brief_data.py`, `files/heartbeat.sh` (warn if the Plaud login stops working, CLI exit code 2).
- `docs/PLAN.md` (Phase 4 → "Plaud memory + customer file", truck debrief replaced, after F0; new
  step "Val's brain" B1–B5 after it), **new** `docs/VAL-BRAIN.md` (Part 5 written out: wiring and ideas 1–32),
  `docs/SETUP-VAL.md` (P1 AutoFlow now, P2 `plaud login`, P3 test recording).
- All test data is made up (the repo is public). Transcripts and timelines live only in the vault.

## Privacy
- Customer files and transcripts live only in the vault on Val's computer and its nightly backup, never in
  git. A customer who asks to be removed: delete their profile facts, timeline and visit files.
- The model runs with Privacy Mode on (Nous Portal).

## Reps later (Phase 5)
Each rep signs in to their own Plaud on their own Val's computer, so recordings never mix. Plaud Team is only
needed if Gerrit wants to hear reps' recordings himself (F11 coaching).

## Built 2026-10-24 (Parts 1–4)
**New files**
- `files/zingas_customer.py` (+ `test_zingas_customer.py`): the customer file. `resolve()` (phone, then email,
  then the F0 follow-up list, then the website's Salesforce match; never a name), `key_for()`, `log()` (one
  timeline entry, deduped by its ref, sorted by time, refreshes "Last 5 contacts"; phone numbers are masked in
  the profile so a number said in passing never matches), `add_facts()` (tagged with source and date, no money
  words, newest 12 per section), `set_sale_stage()`, `move_unmatched()`, `context()` (profile, last 15
  contacts, newest visit summary, "last contact from the customer: N days ago").
- `files/plaud_pickup.py` (+ `test_plaud_pickup.py`, `zingas-plaud.supervisor.conf`): `zingas-plaud run |
  check | backfill | unmatched | match`. Every 2 minutes, 3 Val runs at most per look (new visits first, then
  the backfill, oldest first). The first run lists the last 365 days; old recordings fill memory only (no
  to-dos, drafts or brief notes). "Fresh" = started in the last 24 hours, or listed new and less than 7 days old.
- `files/install-plaud.sh`: puts all of it on Val's computer from the laptop (backs up each old file first;
  `DRY_RUN=1` shows what it would do). Not run yet.

**The Plaud program (checked 2026-10-24, `@plaud-ai/cli` 0.3.15, pinned).** No JSON output except `summary
--json`, so the code reads its text: `plaud recent --days N` (id, name, date, duration per row), `plaud file
<id>` (`start_at`, `created_at`, `duration`, `transcript: available`), `plaud transcript <id> -o <file>`
(`[MM:SS - MM:SS] Speaker: words`), `plaud summary <id> -o <file>`. Exit code 2 = the sign-in does not work.
The sign-in is kept in `~/.plaud/tokens.json` (never in the backup). `plaud login` waits for a browser **on the
same computer** (it listens on port 8199 for 2 minutes), so step P2 happens on Val's own screen. The program
sends Plaud anonymous usage counts (PostHog); no customer data goes there from Val's code. The official MCP
server was not needed.

**Differences from the plan above**
- Matching uses F0's appointment emails first, then the calendar through the website (see Part 2). Window:
  the appointment time is 75 minutes before to 45 minutes after the recording's start. An appointment with a phone but no customer file yet is
  kept under `unmatched-<digits>` and moves to the Prospect ID when the number is matched.
- Unmatched recordings are kept in `plaud/unmatched/` (not under any customer). Their promises still become
  to-dos (who = the name Val heard). Gerrit's answer to the morning-brief line is filed with
  `zingas-plaud match <id> --prospect-id | --phone`.
- Visit drafts go to quo-bridge as category `reply` (never auto-send). A draft with a price is dropped.
- quo-bridge: **no change.** `/api/val/updates` already hands back every approved text with its phone, final
  wording and send time; quo_pickup logs it. Sent F0 follow-ups are logged by `zingas_followups.py`, and
  Gerrit's sent emails by `zingas_inbox.py` (Gmail `in:sent`).
- Every task can carry `customer` (the Prospect ID). New source `visit`. `announce()` no longer checks quiet
  hours; `zingas-todo add` announces. All other Val notes keep quiet hours (a broken Plaud sign-in is told
  once in the day, and in the morning brief).
- Heartbeat: while `/root/.hermes/plaud-login-broken` exists (made by zingas-plaud only after the sign-in had
  worked once), the 10-minute ping reports a failure with "Plaud sign-in stopped", so healthchecks.io warns
  Gerrit.
- The brief gets a `--- VISITS` block: morning = recordings to match, facts that disagree, problems; evening =
  notes to paste into Salesforce. Each line shows once.
- `docs/CONNECTIONS.md` (shared with `app/`): no new route. `zingas-plaud` is one more caller of
  `GET /api/assistant/appointments` (and of the customer route by phone, like zingas-quo). The "Caller" column
  of both copies should say so; left for the session that owns the shared file.

## Verification
1. `python3 files/test_zingas_customer.py`, `python3 files/test_plaud_pickup.py`, and the existing test files.
2. On Val's computer: `zingas-plaud check` lists today's recordings and the login status.
3. Live test: a 2-minute role-play recording during a test calendar event (made-up customer and phone), with
   one promise ("I'll drop off samples Friday"). Within about 5 minutes after it syncs: the visit file, a
   timeline entry, tagged profile facts, a 🟢/🟡 to-do with an alert and the re-sorted list, and the note to
   paste in the evening brief.
4. A text and an email from that test customer each add a timeline entry, and the draft uses one visit detail.
5. A recording with no calendar event shows up once in the morning brief and is not filed anywhere.
6. A to-do added at 9pm on a Saturday sends an alert right away; a normal Val message at that time waits.
7. The test customer's profile shows how they talk, a life event, the house, what Gerrit said and their mood.
