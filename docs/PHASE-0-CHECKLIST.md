# Phase 0: your checklist

These are the sign-ups and approvals only you can do. No code. Do them in this
order. Steps 1 and 3 take the longest, so start them today.

**One rule for every step:** never paste a password or key into a chat or a
text. Put it in 1Password (step 4). The assistant reads it from there.

---

## Start today (these take days or weeks)

### 1. Quo business number and texting registration ⏳ (2026-10-21: all done, waiting on Quo's approval)
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

### 3. Appointment recorder: Plaud ⏳ (2026-10-21: device and Unlimited plan bought, waiting on delivery)
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

### 4. 1Password ✅ (done 2026-10-21: account and both vaults)
- **Why:** every password and key lives here, never in a chat or a text.
- **Do:**
  1. Sign up at 1password.com if you don't have it (Individual is about $3 a month).
  2. Make a vault named exactly **Zingas Assistant** (no apostrophe). In it, make
     one Secure Note named **Assistant Secrets**. Keys Val uses go here.
  3. Make a second vault named exactly **Zingas Bridge**. In it, make one Secure
     Note named **Bridge Secrets**. The keys that text customers go here, so Val
     can never send a text without your tap.
  4. Leave both notes empty for now. Each time a sign-up gives you a key, I'll tell
     you the exact field name to add.
- **Later (when we set up the cloud computer):** you'll make two read-only
  "service accounts", one per vault, in 1password.com under **Developer**. I'll
  walk you through it then.
- **Done when:** both vaults and both notes exist.

### 5. Telegram (first part ✅ done 2026-10-21: app, account, privacy, two-step password)
- **Now** ✅ (about 5 minutes, on the iPhone you carry every day):
  1. App Store → search **Telegram Messenger** (by Telegram FZ-LLC) → Get. Free.
  2. Open it → **Start Messaging**.
  3. Phone number: your **personal cell, the number of this iPhone**. Not the new
     Quo number: that one is for customers only, and it isn't set up yet.
     Telegram only uses your number to sign you in. Val never reads your texts.
  4. Type in the code Telegram sends.
  5. First name **Gerrit**, last name **Huizinga**. A photo is optional.
  6. Settings → Privacy and Security:
     - **Phone Number** → "Who can see my phone number": **Nobody**.
       "Who can find me by my number": **My Contacts**.
     - **Two-Step Verification** → turn it on and make a password. Save it in
       1Password, in your own main vault (called **Personal** or **Private**),
       not the Zingas vaults. This stops
       anyone from taking over the chat that approves customer texts.
- **Later, after Orgo (step 6):**
  - **Val's chat:** the cloud computer shows a QR code. Scan it, tap "Create Bot".
    Nothing to copy.
  - **Approvals chat** (the one with the Approve / Edit / Skip buttons): make a
    second bot by messaging @BotFather in Telegram. Save the code it gives you in
    1Password, in the **Zingas Bridge** vault, never in a chat.

### 6. Orgo (the always-on cloud computer) ✅ (done 2026-10-21: Starter plan, monthly; computer "Val" running)
- **Why:** Val lives here, so she keeps working when your laptop is closed.
- **Plan:** **Starter**, billed **Monthly**: $29 a month (1 computer, 8 GB memory).
  Switch to yearly ($290) once Val has proven herself.
- **Do** (on your laptop, about 10 minutes):
  1. Go to orgo.ai → **Get started**. Sign up with your zingashome.com email.
  2. Choose the **Starter** plan, **Monthly**, and pay.
  3. In the dashboard, click **Launch computer** (or **New computer**, bottom left).
  4. Pick the ready-made **Hermes Agent** computer, not plain Linux or Windows.
  5. Name it **Val**.
  6. Wait until it shows as running. Then stop there.
- **Don't, for now:**
  - Don't add any keys under Settings → Secrets.
  - Don't run any setup inside the computer or connect Telegram. We do that
    together next, with your files.
  - Never click **Stop** on the computer. Stopped means Val is off.
- **Done when:** a computer named Val shows as running in your Orgo dashboard.

### 7. AI account: Nous Portal ✅ (done 2026-10-21: Plus plan, Privacy Mode on)
- **Why:** this is Val's brain, the part that thinks and writes her drafts. One
  sign-in covers Claude, ChatGPT and Grok, so we can run the voice test easily.
- **Plan:** **Plus**, $20 a month (includes $22 of use). If a month runs short,
  we look at it together before you buy more.
- **Do** (on your laptop, about 10 minutes):
  1. Go to portal.nousresearch.com → **Create Account**. Use your zingashome.com
     email. Save the login in 1Password, in your own main vault.
  2. Subscribe to **Plus** ($20 a month).
  3. **Must do:** Account Settings → Privacy Settings → turn on **Privacy Mode**.
     Then Nous doesn't keep what Val sends it. Do this before Val reads anything.
- **Don't:**
  - Don't buy extra top-ups or turn on any automatic refill.
  - Don't connect a ChatGPT account, even though the portal offers it. That
    breaks ChatGPT's rules for an always-on helper.
  - Don't download Hermes Desktop or run anything. Val's computer signs in to
    Nous later, with me. There's no key to copy.
- **Good to know:** with Privacy Mode on, Nous keeps nothing, but the AI company
  behind the brand Val uses (Anthropic, OpenAI or xAI) still gets the message
  and follows its own rules.
- **Done when:** Plus is active and Privacy Mode is on.

### 8. Composio (lets Val read your work email and calendar) ✅ (done 2026-10-21: signed up, free Hobby plan; Google Workspace admin: Delisa)
- **Why:** Composio holds the Google sign-in so Val can read mail, search it,
  write drafts and read your calendar.
- **Safety:** Composio can also send, forward and delete email. So we set it up
  locked down: Val gets only read, search, draft and read-calendar. Its key goes
  in the **Zingas Bridge** vault, which Val can't open, so she can never unlock
  the rest. You still send every email yourself from Gmail.
- **Plan:** **Hobby**, free, no card (100,000 actions a month, far more than Val needs).
- **Do now** (about 5 minutes, on your laptop):
  1. Go to composio.dev → **GET STARTED – FREE**.
  2. Click **Sign up**, then **Continue with email**. Use your zingashome.com email.
  3. Save the login in 1Password, in your own main vault.
  4. Stay on the free Hobby plan.
  5. Find out who runs Google Workspace for zingashome.com. ✅ It's **Delisa**
     (IT). If Google blocks Composio later, Delisa allows it in the Admin console
     (Security → API controls).
- **Don't, for now:**
  - Don't connect Gmail or Calendar.
  - Don't copy any key, and don't set up anything called "Connect" or "AI clients".
  - We do those together on Val's computer, with the locked-down setup.
- **Done when:** you can sign in to the Composio dashboard and you know who your
  Google Workspace admin is.

### 9. healthchecks.io (warns you if Val stops) ✅ (done 2026-10-21: free plan, Email and Telegram warnings connected)
- **Why:** Val checks in with healthchecks.io every 10 minutes. If she goes
  quiet, healthchecks.io warns you. It's a separate company, so the warning
  still comes even if Val's computer is completely down.
- **Plan:** **Hobbyist**, free. The free plan can't send phone texts, so the
  warning comes as a **Telegram message** (from healthchecks.io's own bot, not
  Val's) plus an **email**. Real phone texts need the $20-a-month plan. Skip
  that unless Telegram warnings turn out not to be enough.
- **Do now** (about 5 minutes, laptop and iPhone):
  1. On your laptop, go to healthchecks.io → **Sign Up**.
  2. Type your zingashome.com email → **Email Me a Link**. Open the email and
     click the link. There's no password to save.
  3. If it asks you to name the project, call it **Val**.
  4. On your iPhone, open Telegram → search **@HealthchecksBot** (the one with
     the healthchecks.io logo) → **Start**.
  5. The bot sends you a link. Tap it, choose the **Val** project, and tap
     **Connect Telegram**.
  6. On your laptop, click **Integrations** at the top. Check that **Email**
     and **Telegram** are both listed.
- **Don't, for now:**
  - Don't change or delete any check you see. I set up Val's check-ins later,
    on her computer.
  - Don't pay for a plan.
- **Done when:** Email and Telegram both show under Integrations.

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
