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
| `GET /api/assistant/appointments?day=YYYY-MM-DD&rep=` | Val's briefs | One day of the rep's Google Calendar (Indianapolis time): start, end, all-day, title, place, short note. Cancelled and declined entries left out, dollar amounts taken out. `{connected: false}` until the rep taps "Connect my calendar" (Assistant > Calendar); `reconnect: true` when Google stopped the link. | `src/app/api/assistant/appointments/route.ts`, `src/modules/assistant/calendar.ts`, `calendarStore.ts` |
| `POST /api/assistant/cost` (writes; Val's key, or `QUO_BRIDGE_TOKEN` for quo-bridge) | Val's cost counter (`zingas_money.py`, plan C1) and quo-bridge, about every hour | Saves this month's cost count for the Assistant > Cost tab. Who sent it comes from the key. Each count replaces that sender's last one for the month. Only this month, and last month during the first 7 days. Answers `{ok, month, source}`; nothing to read back. 60 posts per 10 minutes. The shape is below. | `src/app/api/assistant/cost/route.ts`, `src/modules/assistant/cost.ts` |
| `GET /api/assistant/followups?rep=&days=120` | Val, keeping the Follow-Up sheet | Her worklist for one rep: every quoted-but-not-sold visit in the last `days` (1 to 400) plus every follow-up file still open (sold care too). Per customer: name, phone, email, city, the visit, both notes (and whether Val wrote the follow-up note last), the follow-up date in effect and where it came from (`sheet` or `salesforce`), the follow-up file (stage, temperature, waiting on, next step, driver, pause, last contact, fields the rep holds), `valMay` (for each part of the plan: may Val change it today, and why not), the last 5 touches. Soonest follow-up first. Never a price. | `src/app/api/assistant/followups/route.ts`, `src/modules/followups/` |
| `POST /api/assistant/followups/update` (writes) | Val | A note entry, the follow-up date, temperature, waiting on, next step, last contact. The shape and rules are below. | `src/app/api/assistant/followups/update/route.ts`, `src/modules/followups/rules.ts` |
| `POST /api/assistant/followups/touch` (writes) | Val | Logs one touch (text, email, call, visit, note; planned or done). Always allowed. Shape below. | `src/app/api/assistant/followups/touch/route.ts` |
| `GET /api/assistant/events?after=<id>&types=&limit=100` | Val | What happened since `after` (her own place, the last id she handled), oldest first: `{events, last}`. She may read `followup_rep_changed`, `customer_stopped_texts`, `proposal_viewed`, `proposal_signed`, `order_stage_changed`; asking for anything else is a 400. Follow-up events come only for her reps on `VAL_FOLLOWUP_USERS`. | `src/app/api/assistant/events/route.ts`, `src/core/events/store.ts` |

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
- quo-bridge sends only its own lines, for example
  `{"month": "2026-10", "services": [{"id": "quo-texts", "name": "Quo texts", "kind": "texts", "billed": 3.47, "runRate": 4.48, "basis": "count"}], "results": {"texts": 347}}`.

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
`proposal_viewed`, `proposal_signed`, `order_stage_changed`, `customer_stopped_texts`, `fleet_issue_reported`,
`followup_rep_changed`. Val reads them through `GET /api/assistant/events` (above); never `fleet_issue_reported`.

`followup_rep_changed`: a person changed the follow-up date or note on the sheet, or undid one of Val's changes,
on a customer Val keeps follow-ups for. `data`: `{appointmentId, rep, by, fields: ["follow_up_date" |
"followup_note" | ...], action: "edit" | "undo"}`; `prospect_id` is the customer's. Val should re-read that
customer (worklist) before doing anything else for them.

## quo-bridge's door for the website

`GET {QUO_BRIDGE_URL}/api/os/drafts` with `Authorization: Bearer <QUO_BRIDGE_TOKEN>` (quo-bridge's
`ZINGAS_OS_TOKEN`): Val's drafts waiting on Gerrit (name, last 4 digits of the phone, category, text, what the
customer said, status, reasons). Read-only; approving stays in Telegram. Shown on the Assistant section's
Drafts tab. Code: `quo-bridge/os_link.py`, `src/modules/assistant/bridge.ts`.

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
