# Phase 0: your checklist

These are the sign-ups and approvals only you can do. No code. Do them in this
order. Steps 1 and 3 take the longest, so start them today.

**One rule for every step:** never paste a password or key into a chat or a
text. Put it in 1Password (step 4). The assistant reads it from there.

---

## Start today (these take days or weeks)

### 1. Quo business number and texting registration
- **Why:** customers will text this number. The assistant reads and drafts for it.
- **Do:**
  1. Sign up at quo.com with your zingashome.com email. Make it a company
     workspace named "Zinga's".
  2. Pick a local number (317 area code).
  3. In Quo settings, start the business texting registration (carriers call it
     "A2P 10DLC"). You need Zinga's legal name, EIN (tax ID), address and website.
     Ask the owner for the EIN.
  4. When it asks for "sample messages" and "how customers opt in", use the text
     at the bottom of this page.
- **Cost:** about $23 a month (Business plan) plus about $20 one time for registration.
- **Time:** registration approval can take days to a few weeks.
- **Done when:** Quo shows the registration as approved.

### 2. Salesforce notes: ON HOLD
- **Don't ask IT yet.** You chose to wait on Val saving notes into Salesforce.
- **Until then:** Val keeps your notes, follow-up dates and spouse names herself
  and lists them in your evening brief, ready for you to paste into Salesforce.
- When you're ready, I'll give you the exact request to send IT.

### 3. Appointment recorder: Plaud
- **Buy one:** Plaud NotePin S (clip-on, about $179) or Plaud Note Pro (better
  in noisy homes, about $189). Buy from plaud.ai.
- **Plan:** Unlimited (about $240 a year). The free minutes run out in the
  first week.
- **One setting to turn on** in the Plaud phone app: automatic transcripts
  (Plaud calls it "AutoFlow"). Otherwise nothing gets written down.
- **Optional:** in the app's custom words list, add product names you say a
  lot (for example PowerView, Silhouette, pergola) so transcripts spell them right.
- **Don't connect it to anything yet.** Later you'll sign in to Plaud once and
  click "Authorize" so Val can read your transcripts. No password or key to copy.
- **Consent:** already covered. Customers agree to be recorded at the start of
  every appointment (the same as with Rilla).
- **Done when:** the device is charged, the plan is on, and a test recording
  shows a transcript in the app.

---

## Then (each takes about 15 minutes)

### 4. 1Password
- Make a vault named exactly **Zingas Assistant** (no apostrophe). In it, make one
  Secure Note named **Assistant Secrets**. Every key below goes in that note as a
  field. The field names are listed in `files/hermes.env`.
- **Cost:** about $3–5 a month if you don't have 1Password already.

### 5. Telegram
- Install Telegram on your iPhone and make an account. That's all for now. The
  assistant pairs with it later by QR code.

### 6. Orgo (the always-on cloud computer)
- Sign up at orgo.ai. Pick the **Hacker** plan.
- **Cost:** $29 a month.

### 7. AI model account
- Sign up at portal.nousresearch.com (the default in Nick's setup). It is a
  pay-as-you-go API account, not a chat subscription. Add $20 of credit and
  turn off auto top-up, so it can never spend more than you put in.
- During setup on the cloud computer, you sign in once with a code.
- **Do not** connect a ChatGPT sign-in. That breaks ChatGPT's rules for an
  always-on agent.
- (Later, for the voice bake-off, we may add OpenAI, xAI (Grok) or Anthropic keys
  the same way.)

### 8. Composio (connects your Gmail and Calendar)
- Sign up at composio.dev. Connect your **zingashome.com Gmail** and **Google
  Calendar**.
- When Composio asks which actions to allow, pick only: read email, search
  email, create draft, read calendar. **Do not allow "send email".** You send
  every email yourself from the Gmail app.
- If Google says the app is blocked, ask whoever runs the Google Workspace admin to
  allow Composio (Admin console → Security → API controls).
- Save the Composio API key in 1Password.

### 9. healthchecks.io (texts you if the assistant stops)
- Sign up at healthchecks.io. Add your cell number for text alerts.
- **Cost:** free, or about $5 a month for more text alerts.

### 10. Call center contact
- Find out the best email or number to send "customer wants to move their
  appointment" requests to. Write it in 1Password as a note.

---

## Already answered
- Corporate already sends appointment confirmations, so the assistant never will.
- Your personal cell stays personal. It is not moved and not read.

---

## Text for the Quo registration form

**How customers opt in:**
> Customers give their mobile number to their Zinga's design consultant at an
> in-home appointment they booked and agree to receive texts about their quote,
> order and appointment. Reply STOP to opt out.

**Sample message 1:**
> Hi Sarah, this is Gerrit Huizinga with Zinga's. Great meeting you today. I just
> emailed your quote for the living room shades. Any questions, just text me
> here. Thanks! Gerrit

**Sample message 2:**
> Hi Sarah, this is Gerrit with Zinga's. Just checking in on the quote I sent
> Tuesday. Happy to answer anything or come back when you're both home. Reply
> STOP to opt out.
