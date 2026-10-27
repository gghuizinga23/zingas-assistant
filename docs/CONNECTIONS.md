# How Zinga's OS and Val connect

The same file lives in both repos: `app/docs/CONNECTIONS.md` (the website) and `assistant/docs/CONNECTIONS.md`
(Val and quo-bridge). **A change to either side updates both copies.**

Val (the agent on the Orgo computer) and quo-bridge (the texting service on Vercel) are separate programs
with their own keys and their own Supabase project. They never hold the Salesforce key and never read the
website's database. Everything they get from the website goes through the routes below.

## The website's door for Val: `/api/assistant/*`

Every call needs `Authorization: Bearer <ASSISTANT_API_TOKEN>` (Val's key), except the contact route, which
takes quo-bridge's own key `QUO_BRIDGE_TOKEN`. Two keys, so neither program can read what only the other needs. Read-only unless marked. Rate-limited to
120 calls per 10 minutes. Every call is logged without customer details. Only the reps named in
`ASSISTANT_REP_EMAILS` count: Val sees their customers and their numbers, nobody else's. The follow-up routes
and events also need the rep on `VAL_FOLLOWUP_USERS` (403 for anyone else; all four refuse while it is empty).

| Route | Caller | What it gives | Code |
|---|---|---|---|
| `GET /api/assistant/customer?phone=` or `?prospectId=` | Val (plan F1) | One customer's visits, results, follow-up notes, blocked orders. Several matches by phone: a list to pick from. Never a price. | `src/app/api/assistant/customer/route.ts`, `src/modules/assistant/customers.ts` |
| `GET /api/assistant/numbers?rep=&month=YYYY-MM&today=` | Val's Monday brief (F7) | Revenue, goal, sold, close rate, average sale, appointments, demos, revenue per lead, cancel rate. Same maths as the Numbers tab. | `src/app/api/assistant/numbers/route.ts` |
| `GET /api/assistant/contact?phone=` (key: `QUO_BRIDGE_TOKEN`) | quo-bridge, before every customer text | `{ doNotContact, sendWindow: {startHour: 8, endHour: 20} }`. An error means "don't text". | `src/app/api/assistant/contact/route.ts` |
| `POST /api/assistant/contact` `{phone}` (writes; key: `QUO_BRIDGE_TOKEN`) | quo-bridge, when a customer texts STOP to Val's number | Puts them on the shared do-not-contact list, so the estimator never texts them either. | same |
| `GET /api/assistant/appointments?day=YYYY-MM-DD&rep=` | Val's briefs | One day of the rep's Google Calendar (Indianapolis time): start, end, all-day, title, place, short note. Cancelled and declined entries left out, dollar amounts taken out. `{connected: false}` until the rep taps "Connect my calendar" (gear → My profile → Google Calendar); `reconnect: true` when Google stopped the link. | `src/app/api/assistant/appointments/route.ts`, `src/modules/assistant/calendar.ts`, `calendarStore.ts` |
| `GET /api/assistant/day?day=YYYY-MM-DD&rep=` | Val's end-of-day wrap-up (F3) | Every Salesforce visit the rep had that day (Indianapolis day; today when `day` is left out), sold or not, Canceled and No Show too, earliest first: per visit the customer (name, first name, phone, email, city), product, result (`""` until the rep enters it), result detail, follow-up date, lead source and follow-up note. `day` at most 31 days back and 7 ahead, else 400. Never a price. The shape is below. | `src/app/api/assistant/day/route.ts`, `src/modules/assistant/day.ts`, `src/lib/assistant/door.ts` (`dayVisits`) |
| `POST /api/assistant/cost` (writes; Val's key, or `QUO_BRIDGE_TOKEN` for quo-bridge) | Val's cost counter (`zingas_money.py`, plan C1) and quo-bridge, about every hour | Saves this month's cost count for the Assistant > Cost tab. Who sent it comes from the key. Each count replaces that sender's last one for the month. Only this month, and last month during the first 7 days. Answers `{ok, month, source}`; nothing to read back. 60 posts per 10 minutes. The shape is below. | `src/app/api/assistant/cost/route.ts`, `src/modules/assistant/cost.ts` |
| `GET /api/assistant/followups?rep=&days=120` | Val, keeping the Follow-Up sheet | Her worklist for one rep: every quoted-but-not-sold visit in the last `days` (1 to 400) plus every follow-up file still open (sold care too). Per customer: name, phone, email, city, the visit, both notes (and whether Val wrote the follow-up note last), the follow-up date in effect and where it came from (`sheet` or `salesforce`), the follow-up file (stage, temperature, waiting on, next step, driver, pause, last contact, fields the rep holds), `valMay` (for each part of the plan: may Val change it today, and why not), the last 5 touches. Soonest follow-up first. Never a price. | `src/app/api/assistant/followups/route.ts`, `src/modules/followups/` |
| `POST /api/assistant/followups/update` (writes) | Val | A note entry, the follow-up date, temperature, waiting on, next step, last contact. The shape and rules are below. | `src/app/api/assistant/followups/update/route.ts`, `src/modules/followups/rules.ts` |
| `POST /api/assistant/followups/touch` (writes) | Val | Logs one touch (text, email, call, visit, note; planned or done). Always allowed. Shape below. | `src/app/api/assistant/followups/touch/route.ts` |
| `GET /api/assistant/events?after=<id>&types=&limit=100` | Val | What happened since `after` (her own place, the last id she handled), oldest first: `{events, last}`. She may read `followup_rep_changed`, `customer_stopped_texts`, `proposal_viewed`, `proposal_question`, `proposal_signed`, `order_stage_changed`; asking for anything else is a 400. Follow-up events come only for her reps on `VAL_FOLLOWUP_USERS`. | `src/app/api/assistant/events/route.ts`, `src/core/events/store.ts` |
| `POST /api/assistant/upcoming` (writes; Val's key) | Val's follow-ups program (`zingas_followups.py`), about every 15 minutes and right after the day's list is made or sent | Saves the follow-ups the coming weekday lists will hold (14 days ahead), for the Assistant > Drafts tab's "Coming up". Each list replaces the last, so a reply, a sale or a new estimate shows on the next one. Sends nothing: each follow-up still reaches Telegram on its day and needs Gerrit's tap. Answers `{ok, drafts}`; nothing to read back. 30 posts per 10 minutes. The shape is below. | `src/app/api/assistant/upcoming/route.ts`, `src/modules/assistant/upcoming.ts` |
| `POST /api/assistant/todo` (writes; Val's key) | Val's to-do sender (`zingas-todo watch`, supervisord program `zingas-todo-post`), on every change to the list and at least every 10 minutes | Saves Gerrit's open to-do list for the Assistant > To-do tab. Each list replaces the last. The page moves a message with no answer past 24 hours to Now itself (Gerrit's rule, 2026-10-26), the same as Val. Answers `{ok, items}`; nothing to read back. 120 posts per 10 minutes. The shape is below. | `src/app/api/assistant/todo/route.ts`, `src/modules/assistant/todo.ts` |
| `GET /api/assistant/issues?rep=` | Val's to-do sender (`zingas-todo watch`, `IssueSync`), every 2 minutes | The rep's blocked orders, as on the Issues tab (Gerrit, 2026-10-26: each one is a Today task, Now after 24 hours). Salesforce is read again at most every 2 minutes. Per order: id, customer, products, job number, `waitingOn`, `task`, turned in, days blocked, the last 5 comments, a link that opens it on the Issues tab. Never the balance due, never an amount. Shape below. | `src/app/api/assistant/issues/route.ts`, `src/modules/assistant/issues.ts`, `assistant/files/zingas_todo.py` (`IssueSync`) |
| `GET` and `POST /api/assistant/todo/changes` (Val's key) | Val's to-do sender (`zingas-todo watch`), every 15 seconds | Gerrit's clicks on the To-do tab (Done, priority, due date, words, remove, undo). GET gives the ones Val hasn't made yet, oldest first; Val makes each on her list with plain code (the same rules as Telegram) and POSTs how each went. The page shows a click at once and, for an hour, any Val couldn't make. Table `assistant_todo_changes`. 200 calls per 10 minutes. The shape is below. | `src/app/api/assistant/todo/changes/route.ts`, `src/modules/assistant/todoStore.ts`, `assistant/files/zingas_todo.py` (`Changer`) |
| `POST /api/assistant/lessons` (writes; Val's key) | Val's learning program (`zingas-voice run`, supervisord program `zingas-voice`), on every change and at least every 10 minutes | Saves what Val learned from Gerrit's edits, for the Assistant > What Val learned tab: this week's "sent with no change" numbers and every lesson in use (removed ones are left out) with the two versions that taught it. Each list replaces the last. Answers `{ok, lessons}`; nothing to read back. 503 until its tables are made. 60 posts per 10 minutes. The shape is below. | `src/app/api/assistant/lessons/route.ts`, `src/modules/assistant/lessons.ts`, `assistant/files/zingas_voice.py` |
| `GET` and `POST /api/assistant/lessons/changes` (Val's key) | `zingas-voice run`, every 15 seconds | Gerrit's clicks on the What Val learned tab: Remove (a wrong lesson) and Make it a rule. Same pattern as the to-do clicks: GET gives the ones Val hasn't made yet, Val makes each with plain code and POSTs how each went. Table `assistant_voice_lesson_changes`. 200 calls per 10 minutes. The shape is below. | `src/app/api/assistant/lessons/changes/route.ts`, `src/modules/assistant/lessonsStore.ts`, `assistant/files/zingas_voice.py` (`Runner`) |

The estimator's older routes for Val (`/api/estimator/assistant/*`, the signed webhook to quo-bridge) still
work as documented in `docs/ESTIMATOR.md`.

## Val's cost count (`POST /api/assistant/cost`)

Dollars as plain numbers (`18.4`), `null` for "don't know" (shown as —, never $0). Everything but `month` may
be left out. A count with anything wrong is refused whole with a 400 and the reason, so it never half-replaces
a good one. Val's own costs only: no customer, quote or sale goes in it.

```json
{
  "month": "2026-10",
  "services": [
    { "id": "nous", "name": "Nous Portal", "kind": "ai", "billed": 18.4, "runRate": 23.75, "basis": "estimate" },
    { "id": "orgo", "name": "Orgo", "kind": "plan", "billed": 29, "basis": "receipt" },
    { "id": "chatgpt", "name": "ChatGPT", "kind": "ai", "billed": 20, "basis": "receipt", "personal": true }
  ],
  "subscriptions": [
    { "id": "orgo", "name": "Orgo", "cost": 29, "cycle": "month", "nextRenewal": "2026-11-03", "unused": false }
  ],
  "credits": { "name": "Nous credits", "left": 6.5, "daysLeft": 9 },
  "limits": [{ "name": "Composio", "used": 12000, "limit": 100000, "unit": "actions" }],
  "results": { "texts": 347, "draftsApproved": 40, "followUps": 22, "leadsAnswered": 5 }
}
```

- `kind`: `ai`, `texts`, `plan`, `storage`, `tools` or `other`. `basis`: `receipt` (the real bill), `count`
  (counted exactly, like texts sent × price) or `estimate` (use × a price table, checked against the receipt
  each month).
- `billed`: charged so far this month. `runRate`: a full month at this pace (left out: `billed` stands in).
- `personal: true`: one of Gerrit's own sign-ups, not Val's stack. Shown to admins only.
- `id`s: short, lower case, unique in their list. When Val and quo-bridge both send a line with the same `id`
  (the texts, `quo-texts`), quo-bridge's wins.
- Texts are paid from Quo's prepaid credits. Val counts the cash from the top-up receipt (her line
  `quo-credits`), so quo-bridge's `quo-texts` line adds $0 and its name says what the texts used of the credits.
- quo-bridge sends only its own lines, for example
  `{"month": "2026-10", "services": [{"id": "quo-texts", "name": "Quo texts ($3.47 so far, paid from prepaid credits)", "kind": "texts", "billed": 0, "runRate": 0, "basis": "count"}], "results": {"texts": 347}}`.

## Val keeps the Follow-Up sheet (`/api/assistant/followups/*`)

The follow-up date and the follow-up note stay where the sheet keeps them (`notes.follow_up_date`, the
follow-up note), so the Today tab, the calendars and the morning email see Val's changes with no extra step.
What's new is a follow-up file per appointment (`followup_cases`), a touch log (`followup_touches`) and a change
log (`followup_changes`), from `supabase/migrations/20261024000400_followup_cases.sql`. Until that runs, these
routes answer 503.

**Update.** Every field but `appointmentId` may be left out; `prospectId` is needed on Val's first write to an
appointment (it proves the customer is one of her reps'). Unknown fields, bad values or a dollar amount anywhere:
400, nothing written.

```json
{
  "appointmentId": "a0X...", "prospectId": "a0Y...",
  "note": "Texted about the shade samples, no answer yet",
  "followUpDate": "2026-10-29",
  "temperature": "warm",
  "waitingOn": "spouse", "waitingOnDetail": "Husband back from travel Monday",
  "nextStep": "Call Tuesday after 5",
  "lastContact": { "at": "2026-10-24T15:10:00-04:00", "by": "val" }
}
```

- `note`: one line, at most 500 characters. It goes on top of the follow-up note as
  `10/24/26 - Texted about the shade samples, no answer yet; Val` (the sheet's "New entry" format), and never
  over a change a rep is making at the same moment.
- `temperature`: `hot`, `warm`, `cold`. `waitingOn`: `customer`, `spouse`, `financing`, `hoa`, `quote_change`,
  `timing`, `other`. `waitingOnDetail` and `nextStep`: at most 300 characters. `null` clears.
- `lastContact.by`: `val`, `rep` or `customer`. Only ever moves forward in time.
- Answer: `{ok, applied, refused: [{field, reason}], followUpDate, noteUpdatedAt, changeIds}`. 200 when anything
  went in, 409 when nothing did.

**The rep always wins** (`src/modules/followups/rules.ts`):

- A date or field the rep set by hand is refused to Val until it runs out: a date holds through that date, other
  fields through the follow-up date in effect when the rep set them, or until the rep hands them back. A
  follow-up date already on the sheet when Val first writes to an appointment counts as the rep's.
- Driver `rep` ("I've got this") and a pause (`pausedUntil`, through that day): Val may add notes, log touches and
  record the last contact, but not change the date, temperature, waiting on or next step.
- Closed cases (`closed_sold`, `closed_lost`): the same.
- Everything Val writes is stamped `val@assistant.zingas` (the sheet shows "Val") and logged with the value
  before. The rep can undo it on the sheet; an undone field becomes the rep's.

**Touch.**

```json
{ "appointmentId": "a0X...", "prospectId": "a0Y...", "channel": "text", "direction": "out", "by": "val",
  "summary": "Asked if Tuesday works", "source": "quo", "status": "sent", "at": "2026-10-24T15:10:00-04:00" }
```

`channel`: `text`, `email`, `call`, `visit`, `note`. `direction`: `out`, `in` or left out. `by`: `val`,
`customer` or the rep's email (default `val`). `source`: `quo`, `gmail`, `rep_update`, `salesforce`,
`estimator`, `recording`. `status`: `planned`, `approved`, `sent` (default; means it happened), `skipped`.
`summary`: at most 1000 characters, never a price. `at` defaults to now.

## Shared rules

- **Do-not-contact:** one list, in the website's database (`do_not_contact`, `src/core/contact`). A STOP sent to
  either number lands on it; only START (to the estimator's number) or Gerrit clears it.
- **Send window:** 8am to 8pm in the customer's time zone, for every customer text
  (`src/core/contact/rules.ts` and `quo-bridge/send_gate.py`, kept the same).
- **No prices** in anything Val reads or sends.
- **Every customer message needs Gerrit's approval tap**, except the narrow auto-send kinds in `send_gate.py`.

## Events

The website keeps "something happened" notes in `os_events` (`src/core/events/store.ts`). Names in use:
`proposal_viewed`, `proposal_question`, `proposal_signed`, `order_stage_changed`, `customer_stopped_texts`,
`fleet_issue_reported`, `followup_rep_changed`. Val reads them through `GET /api/assistant/events` (above); never
`fleet_issue_reported`.

What really writes each one today (2026-10-26):

| Event | Written by | When |
|---|---|---|
| `followup_rep_changed` | the Follow-Up sheet and page (`src/modules/followups/service.ts`) | below |
| `customer_stopped_texts` | the contact route (quo-bridge's STOP) and the estimator's own text inbox (`src/lib/inboundText.ts`) | a customer texts STOP |
| `proposal_viewed` | the customer's proposal page (`src/app/(customer)/p/[token]/page.tsx`) | the customer opens their link, at most once per 30 minutes; never the rep's in-person hand-off |
| `proposal_question` | "Ask a question" on that page (`askQuestion`, `src/actions/customer.ts`) | the customer sends a question |
| `proposal_signed` | signing (`signCore`, `src/lib/proposal/signing.ts`) | the customer signs, on their link or the rep's iPad; never demo data |
| `fleet_issue_reported` | Fleet (`src/modules/fleet/actions.ts`) | a car problem is reported |
| `order_stage_changed` | nothing yet | (Val may ask for it; none come back until something writes it) |

The three proposal events (`src/lib/assistant/proposalEvents.ts`) are written right after the page or the
signing is done, at the same spots as the rep's alert and the old assistant webhook, and only when the proposal's
rep is in `ASSISTANT_REP_EMAILS`. The estimator itself is still behind `ESTIMATOR_USERS` (Gerrit only). A write that
fails is logged and dropped: it never breaks the customer's page or the signing. `source` is `estimator`;
`prospect_id` is the customer's Salesforce Prospect id when the estimator customer has one (came from a Salesforce
appointment), else null. `data` never holds a price, total or payment method:

- `proposal_viewed`: `{proposalId, title, viewCount, firstViewedAt, lastViewedAt, sentAt, customerName, customerPhone,
  customerEmail, repEmail}`. Times are ISO (UTC) or null; phone and email are null when the customer has none.
- `proposal_question`: the same, plus `question` (the customer's words, cut to 500 characters; the whole question
  is on the job in the estimator).
- `proposal_signed`: `{proposalId, title, signedAt, customerName, customerPhone, customerEmail, repEmail}`.

`followup_rep_changed`: a person changed the follow-up date or note on the sheet, undid one of Val's changes, or
pressed a button on the Follow-Up page run by Val, on a customer Val keeps follow-ups for. `data`: `{appointmentId,
rep, by, fields: ["follow_up_date" | "followup_note" | "driver" | "paused_until" | "stage" | ...], action: "edit" |
"undo" | "mine" | "val" | "snooze" | "date" | "sold" | "lost" | "update"}`; `prospect_id` is the customer's.
`mine` is "I've got this", `val` is "Val, take it back", `update` is "Tell Val what happened" (the rep's words are
the newest entry on the follow-up note, never in the event). Val should re-read that customer (worklist) before
doing anything else for them.

## End-of-day wrap-up and hot-lead alerts (F3, F8)

- **Wrap-up (F3).** For her end-of-day wrap-up Val reads `GET /api/assistant/day` for the rep's day: every visit,
  with `result: ""` for the ones the rep hasn't resulted yet. The door is read-only; results are still entered in
  Salesforce.

```json
{ "day": "2026-10-26", "rep": "gerrithuizinga@zingashome.com",
  "visits": [{ "appointmentId": "a0Y5e000001", "prospectId": "a0X5e000001", "time": "15:00",
               "customer": { "name": "Walter, Natalie", "firstName": "Natalie", "phone": "(317) 555-0101",
                             "email": "natalie@example.com", "city": "Carmel" },
               "product": "Int - Shutters", "result": "Demoed, Not Sold", "resultDetail": "Price",
               "followUpDate": "2026-10-30", "leadSource": "Google",
               "note": "10/26/26 - Wants samples; Gerrit" }] }
```

  `rep` is the rep's email. `prospectId`, `email`, `resultDetail`, `followUpDate` and `note` can be null; `time` is
  24-hour `HH:MM`. `result` is one of `Sold`, `Demoed, Not Sold`, `Not Demoed`, `Canceled`, `No Show`, or `""`.
- **Hot-lead alerts (F8).** Val reads `proposal_viewed`, `proposal_question` and `proposal_signed` from
  `GET /api/assistant/events` for her hot-lead alerts (a customer looking at their proposal right now is a good
  moment to call). The rep still gets the estimator's own text as before. The events route also needs the rep on
  `VAL_FOLLOWUP_USERS`, like every follow-up route. These events only come for proposals made in the
  estimator, so for now only Gerrit's (the estimator is his only until he says it is shipped).

## quo-bridge's door for the website

`GET {QUO_BRIDGE_URL}/api/os/drafts` with `Authorization: Bearer <QUO_BRIDGE_TOKEN>` (quo-bridge's
`ZINGAS_OS_TOKEN`): Val's drafts waiting on Gerrit (name, last 4 digits of the phone, category, text, what the
customer said, status, reasons, `edited`, `can_edit`). Shown on the Assistant section's Drafts tab. Follow-ups
still on their day's list (`planned`, not approved yet) are in it too (2026-10-26), with `batch_id` (the list's day,
YYYY-MM-DD), `touch`, `due_at`, and the email that goes with each (`email_subject`, `email_body`; "" when none).

`POST {QUO_BRIDGE_URL}/api/os/drafts/action`, same code: Gerrit's button on one draft (Drafts tab, 2026-10-26).
`{"id", "action": "edit" | "approve" | "send_now" | "skip", "text"?}`, or `{"batch": "YYYY-MM-DD", "action":
"approve_all"}`: a day's follow-up list, the same as Approve all on its Telegram card (each sends at its time, ones
already due now; answers `{ok, approved, message}`). `edit` saves new words (still waiting);
`approve` is Gerrit's approval, the same as his Telegram tap (with `text`, the new words go first); `send_now`
sends a text held until 8 AM (409 for a follow-up: it waits for its time and its email); `skip` never sends it. quo-bridge runs the same send gate as for a tap (quiet hours,
do-not-contact, the 8 AM hold) and updates the Telegram card. Answers `{ok, status, message}`; 409 when the
draft was already handled. The website lets only people `ASSISTANT_USERS` names press these (Gerrit). Code:
`quo-bridge/bridge.py` (`os_action`), `src/modules/assistant/bridge.ts`, `src/modules/assistant/actions.ts`.

When quo-bridge can't reach the website's contact route, it treats the customer as do-not-contact (never text
when unsure), for 30 seconds before trying again.

## Settings that must match on both sides

| Website (Vercel `zingas-sales-dashboard`) | Val / quo-bridge | Same value? |
|---|---|---|
| `ASSISTANT_API_TOKEN` | Val's own setting for calling the website | Yes |
| `QUO_BRIDGE_TOKEN` | quo-bridge (Vercel): `ZINGAS_OS_TOKEN` | Yes, and different from `ASSISTANT_API_TOKEN` |
| `QUO_BRIDGE_URL` | (quo-bridge's own address) | |
| `APP_URL` | quo-bridge: `ZINGAS_OS_URL` | Yes |
| `ASSISTANT_REP_EMAILS` | (none) | |
| `VAL_FOLLOWUP_USERS` | (none) | Whose follow-ups Val keeps (Gerrit first). Also needs the rep in `ASSISTANT_REP_EMAILS`. |

## Val's to-do list (`POST /api/assistant/todo`)

```json
{
  "madeAt": "2026-10-26T18:00:00+00:00",
  "items": [{ "id": "a1b2c3d4e5f6", "n": 1, "task": "Call back Pat about shutters", "who": "Pat Lee",
              "priority": "today", "source": "text", "replyBy": "2026-10-27T15:00:00+00:00", "due": null,
              "why": "", "link": "", "addedAt": "2026-10-26T15:00:00+00:00",
              "receivedAt": "2026-10-26T15:00:00+00:00",
              "sources": [{ "kind": "text", "at": "2026-10-26T15:00:00+00:00", "from": "Pat Lee", "subject": "",
                            "text": "Can you come Tuesday?", "link": "" }] }],
  "done": [{ "id": "f6e5d4c3b2a1", "task": "Send the brochure", "who": "", "closedAt": "2026-10-26T16:00:00+00:00" }]
}
```

- `items`: the open tasks, at most 500. `priority`: `now`, `today`, `week`, `later` (the one Val saved).
  `source`: `email`, `text`, `call`, `voicemail`, `visit`, `issue`, `gerrit`, `val`. `replyBy`: messages and
  blocked orders only, 24 hours after it came in (an order: after Val first saw it). `due`: `YYYY-MM-DD` or null. `link`: https only (the newest email's).
- `receivedAt`: when the task came in (its first message, visit or ask). `sources` (2026-10-26): every message
  behind the task, oldest first, at most 10: `kind` (a `source` word), `at`, `from`, `subject` (emails; "Visit on
  Oct 23" for a visit), `text` (at most 600 characters: the email's start, the text, the voicemail, the visit
  summary, or Gerrit's own words), `link` (https only; Gmail links are fixed by the page to open the signed-in
  person's own inbox). Both are optional: a list without them gets one source made from the task.
- `done`: tasks finished in the last 24 hours, at most 100. `id` lets the page's Undo put one back.
- Never a task's `ref` (it can hold a phone number), never a price (amounts are taken out on the way in, message
  words too).

Gerrit's clicks (`/api/assistant/todo/changes`):

```json
GET  -> { "changes": [{ "id": "<uuid>", "itemId": "a1b2c3d4e5f6", "action": "priority", "value": "now",
                        "madeAt": "2026-10-26T18:01:00+00:00" }] }
POST <- { "results": [{ "id": "<uuid>", "ok": true, "message": "Priority changed." }] }
```

- `action`: `done`, `drop` (remove, not counted as done), `undo` (put a done task back), `priority`
  (`now`/`today`/`week`/`later`; a message stays at `today` or higher), `due` (`YYYY-MM-DD`, or `""` to clear),
  `task` (new words, at most 160, amounts taken out).
- A click is made once. If the POST fails, Val sends the same answer again on her next look; the website keeps
  the first answer. `message` shows to Gerrit when `ok` is false; it never holds a phone number or a price.

## What Val learned from Gerrit's edits (`POST /api/assistant/lessons`)

Added 2026-10-26 (assistant `files/zingas_voice.py`, `website_body`). Every time Gerrit sends something
different from Val's draft (an edited text or follow-up, an edited Gmail draft, or a text he typed himself in the
Quo app), Val saves both versions and writes one short lesson. Lessons go into her next drafts at once.

```json
{
  "at": "2026-10-26T22:00:00+00:00",
  "week": { "drafts": 12, "unchanged": 7, "last_drafts": 10, "last_unchanged": 4,
            "by_channel": { "text": { "drafts": 9, "unchanged": 6 }, "email": { "drafts": 3, "unchanged": 1 } } },
  "lessons": [{ "id": "L3", "date": "2026-10-26T18:04:00+00:00", "channel": "text", "category": "reply",
                "kind": "edited", "customer_name": "Pat", "customer_said": "Do you have anything Thursday?",
                "val_wrote": "Hi Pat, this is Gerrit Huizinga with Zinga's. Thursday could work soon.",
                "gerrit_sent": "Hi Pat, Thursday at 2 works. See you then!",
                "lesson": "Drop the intro line when the customer already knows Gerrit.",
                "status": "active", "seen": 2, "proposed": true }]
}
```

- `week`: the 7 days before `at` and the 7 before that. A draft counts when it was sent (unchanged or edited) or
  Gerrit answered himself instead; skipped drafts don't count.
- `lessons`: at most 500, newest first. `channel`: `text` or `email`. `kind`: `edited` (Gerrit changed Val's
  draft) or `rewrote` (he answered himself instead). `status`: `active` or `rule` (Gerrit made it a permanent
  rule in VOICE.md). `seen`: how many edits taught the same idea. `proposed`: offered as a rule (seen 2 or more
  times; at most 5). `customer_name` is a first name only. Never a phone number or email address.
- Text fields are at most 2,000 characters; `lesson` at most 200.

Gerrit's clicks (`/api/assistant/lessons/changes`), the same shape as the to-do clicks:

```json
GET  -> { "changes": [{ "id": "<uuid>", "itemId": "L3", "action": "remove", "madeAt": "2026-10-26T18:01:00+00:00" }] }
POST <- { "results": [{ "id": "<uuid>", "ok": true, "message": "Removed. Val will not use it again." }] }
```

- `action`: `remove` (the lesson is wrong: it stops at once and never comes back; a rule also leaves VOICE.md)
  or `rule` (make it a permanent rule in VOICE.md). The next list Val sends no longer has a removed lesson.
- A click is made once. If the POST fails, Val sends the same answer again on her next look.

## Blocked orders for Val (`GET /api/assistant/issues`)

```json
{ "rep": "Gerrit Huizinga", "syncedAt": "2026-10-26T21:00:00.000Z",
  "issues": [{ "id": "a0X5e000001", "customer": "Bruhn, Tim", "products": ["Pergolas"], "jobNumber": "3536",
               "waitingOn": "Order info", "task": "Send Customer Success the order info",
               "turnedInOn": "2026-10-20", "daysBlocked": 6,
               "comments": [{ "date": "10/25/26", "text": "Need the fabric color; KJC" }],
               "link": "https://<site>/issues?open=a0X5e000001" }] }
```

Only orders that wait on Gerrit: one waiting on the market manager's approval is left out (Gerrit, 2026-10-26), so
its task is closed on Val's side like any order that leaves the list (`waitsOnGerrit` in
`src/modules/assistant/issues.ts`).

- Val's side (`IssueSync`, every 2 minutes): a new order is a task with source `issue`, priority `today` and a
  24-hour clock from when Val first saw it (`replyBy`; Now after that), and Gerrit is told at once. A new comment
  or a new `waitingOn` goes on the open task (a new task if Gerrit closed the old one). An order that leaves the
  list is done. An error or no answer changes nothing. What Val has seen: `todo/issues.json` in her vault.

## Val's coming follow-ups (`POST /api/assistant/upcoming`)

Val works these out with the same rule as the day's real list (missed touches fold into the newest one; a
Friday list holds the weekend), from the next list day (tomorrow once today's list is made) for `days_ahead`
days. Today's list is left out: it shows under "Waiting" once quo-bridge has it. A list with anything wrong is
refused whole with a 400 and the reason, so it never replaces a good one. Dollar amounts are taken out.

```json
{
  "made_at": "2026-10-24T16:15:00+00:00",
  "days_ahead": 14,
  "items": [
    { "list_day": "2026-10-26", "send_at": "2026-10-26T12:05:00+00:00", "customer_name": "Pat Testerson",
      "touch": "7 days", "written_by": "fixed", "text": "Hey Pat! ...", "email_subject": "...", "email_body": "...", "note": "" },
    { "list_day": "2026-10-26", "send_at": "2026-10-26T12:05:00+00:00", "customer_name": "Sam Example",
      "touch": "after reply 1", "written_by": "val", "text": "", "email_subject": "", "email_body": "",
      "note": "Val couldn't write this one yet; she tries again shortly." }
  ],
  "held": [{ "customer_name": "Cy Sample", "why": "they wrote back", "back_on": "2026-10-27" }]
}
```

- `list_day`: the morning it reaches Telegram. `send_at`: when it goes out once approved.
- `written_by`: `fixed` (Gerrit's standard wording) or `val` (Val wrote it from the conversation). Val writes a
  personal one ahead once and keeps it until the conversation changes, so the preview is what gets posted.
- `note`: why there's no text yet, or that Val would close the customer instead. Each item needs a text or a note.
- `held`: customers paused because they wrote back; follow-ups start again after 3 quiet days (`back_on`).
- At most 300 items and 200 held.
