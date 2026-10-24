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
`ASSISTANT_REP_EMAILS` count: Val sees their customers and their numbers, nobody else's.

| Route | Caller | What it gives | Code |
|---|---|---|---|
| `GET /api/assistant/customer?phone=` or `?prospectId=` | Val (plan F1) | One customer's visits, results, follow-up notes, blocked orders. Several matches by phone: a list to pick from. Never a price. | `src/app/api/assistant/customer/route.ts`, `src/modules/assistant/customers.ts` |
| `GET /api/assistant/numbers?rep=&month=YYYY-MM&today=` | Val's Monday brief (F7) | Revenue, goal, sold, close rate, average sale, appointments, demos, revenue per lead, cancel rate. Same maths as the Numbers tab. | `src/app/api/assistant/numbers/route.ts` |
| `GET /api/assistant/contact?phone=` (key: `QUO_BRIDGE_TOKEN`) | quo-bridge, before every customer text | `{ doNotContact, sendWindow: {startHour: 8, endHour: 20} }`. An error means "don't text". | `src/app/api/assistant/contact/route.ts` |
| `POST /api/assistant/contact` `{phone}` (writes; key: `QUO_BRIDGE_TOKEN`) | quo-bridge, when a customer texts STOP to Val's number | Puts them on the shared do-not-contact list, so the estimator never texts them either. | same |
| `GET /api/assistant/appointments?day=` | Val's daily brief | Not built yet: waits on the Google Calendar check (go-live list). | |

The estimator's older routes for Val (`/api/estimator/assistant/*`, the signed webhook to quo-bridge) still
work as documented in `docs/ESTIMATOR.md`.

## Shared rules

- **Do-not-contact:** one list, in the website's database (`do_not_contact`, `src/core/contact`). A STOP sent to
  either number lands on it; only START (to the estimator's number) or Gerrit clears it.
- **Send window:** 8am to 8pm in the customer's time zone, for every customer text
  (`src/core/contact/rules.ts` and `quo-bridge/send_gate.py`, kept the same).
- **No prices** in anything Val reads or sends.
- **Every customer message needs Gerrit's approval tap**, except the narrow auto-send kinds in `send_gate.py`.

## Events

The website keeps "something happened" notes in `os_events` (`src/core/events/store.ts`). Names in use:
`proposal_viewed`, `proposal_signed`, `order_stage_changed`, `customer_stopped_texts`, `fleet_issue_reported`.
Val does not read them directly yet; when it does, it will be through a new door route listed here.

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
