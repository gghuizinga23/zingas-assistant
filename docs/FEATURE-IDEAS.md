# New feature short-list (from Gerrit's answers, 2026-10-22)

Gerrit's answers:
- **Sale stage:** after the install.
- **Problems:** all four (quotes go quiet, missing decision maker, price or competitor, admin after hours).
- **In the truck:** typing is fine.
- **Money ideas:** all four.
- **Install list:** work Gmail, label **Completed**.
- **Missed calls:** Gerrit's tap, always.
- **Numbers:** Sales Dashboard metrics, not commission.

Every customer text still waits for Gerrit's tap. Every number shown is copied from a real source; Val never makes up a price or a figure.

| # | Feature | What it does | Needs | Size |
|---|---|---|---|---|
| 1 | **Missed-call text-back** | A missed call or voicemail on the Quo number becomes a "Sorry I missed you, I'm in a home. Can I call you at 3?" draft in Val Approvals within a minute. The time comes from the next gap in the calendar | Nothing new. quo-bridge already gets Quo's call alerts | Small |
| 2 | **After-install program** | Starts from new emails under the Gmail label **Completed**. Day 3: a "How are they working?" text. A problem goes straight to Gerrit, and that customer gets no review ask. A happy reply leads to a Google review ask, then a referral ask a week later, then an "other rooms" or spring outdoor check-in at 6 to 12 months | Zinga's Google review link; whether there is a referral reward | Medium |
| 3 | **End-of-day wrap-up** | 5:30 PM: one Telegram card per appointment that day, with Sold / Thinking / Lost buttons and one typed line. Val turns that into the Salesforce note (to paste, while write access is on hold), the follow-up date, and the start of the right follow-up plan | Nothing new | Small–medium |
| 4 | **Quiet-quote rescue** | A follow-up plan with a reason in each touch: a question answered, a product photo, a season. A final, polite "Should I close your file?" text, which often gets a reply. Hot-lead alerts ("Sarah opened the proposal 3 times, call now") once the Estimator link exists | Estimator Phase 1.5 for the alerts | Medium |
| 5 | **Spouse pack** | After a visit where one decision maker was missing: a short, clear summary for the other one (what they picked, why, the next step), as an email draft or text | Plaud for the best version; before Plaud, a typed line from the wrap-up | Small after #3 |
| 6 | **Price and competitor answers** | When a customer mentions Budget Blinds, Home Depot, Costco or "too expensive", the draft uses Gerrit's own value points (warranty, measure and install, motorization, local service). Never a price | Gerrit's talking points; Val learns more from his edits | Small |
| 7 | **Monday numbers** | In the Monday morning brief: Revenue against goal, Sold, Close rate, Average sale, Demos and Appts, Revenue per lead, Cancel rate, plus open quotes | Read-only access to the dashboard's numbers (a read-only view, never the dashboard's full key) | Medium |
| 8 | **Coaching from recordings** | After each visit: the objections raised and how Gerrit answered them. Once a month: patterns in what wins and what loses deals. For Gerrit only | Plaud | Medium |

**Added 2026-10-22 (Gerrit liked both):**
- **Neighbor effect:** a project under **Completed** flags open quotes on the same street, with a "we just
  finished a project near you" draft. It never names the neighbor or gives their address.
- **Weather nudge:** the first hot week brings open outdoor-shade, screen and pergola quotes back. It must be
  ready by about April 2027.

**Added 2026-10-22 (Gerrit's idea): Know the customer before every reply (F1).**
A text from any number starts a lookup in this order:
1. Val's memory notes.
2. Salesforce data: appointments, products, results and quotes.
3. The Estimator: proposals, views and questions.
4. Gmail threads, including the **Completed** label.
5. The full Quo text history.

Then Val writes a one-page customer brief and decides where the customer is in the sale. She drafts the
way Gerrit would from that point. The Approve card shows who this is above the draft.

Today Val checks only her own notes. The new part is a narrow, read-only lookup service that returns one
customer's records for one phone number, so no full Salesforce or dashboard key is ever on Val's computer.
The amounts quoted help Val understand the deal, but they never go into a text.

**Build order:** this is in `docs/PLAN.md`, under "New features", as F1 to F11: know the customer, missed-call text-back,
end-of-day wrap-up, after-install program, neighbor effect, price and competitor answers, Monday numbers,
quiet-quote rescue, weather nudge, spouse pack, coaching. Not started.

**Added 2026-10-23 (Gerrit's idea): money tracker, ROI and the Assistant tab.**
A running total of everything Gerrit pays for (Val's stack and his own AI and tool sign-ups), live from
Val's own use and checked against the real receipts. A Monday money block, a monthly statement, alerts
(credits about to run out, a cost spike, renewals, free-plan limits, unused services), and an ROI with two
numbers: jobs Val touched and jobs Val revived, valued at the sale amount plus time saved at $40/hour.
Later: cost per rep, a cheaper-model check and a year-end tax export. It all shows in a new Assistant tab in
the Sales Dashboard (Gerrit only), with Val's work, the follow-up pipeline, voice and trust, and health.
Details and build steps C1–C7 are in `docs/PLAN.md`, "Money: costs and ROI" (Build order step 5).

**Added 2026-10-26 (Gerrit's idea): temp shades by Amazon (F12).**
A customer who asks for temporary shades (in the visit, or by text or email) gets them ordered from a
dedicated Zinga's Amazon account with its own virtual card and shipped straight to their home. Val confirms
where to ship (never guessed) and how many from the window sizes (never on sliding doors), and every order
waits for Gerrit's tap. Once a month she emails payments@ the list of orders and invoices for reimbursement.
Details in `docs/PLAN.md`, "F12: Temp shades by Amazon" (Build order step 9b).
