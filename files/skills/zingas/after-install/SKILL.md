---
name: after-install
description: The after-install texts (plan F4) from the Gmail label Completed, and how to save Gerrit's Google review link and referral reward.
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, Installs, Reviews, Referrals, Customers]
---

# After the install

The program `zingas-installs` does this by itself. It reads new emails under the work Gmail label **Completed**
(Gerrit's install list) and makes cards in Val Approvals. Nothing sends without Gerrit's Approve tap.

1. 3 days after the install: "How are they working?"
2. Their answer: the text pickup knows they are answering it. Happy: the reply thanks them and asks for a Google
   review with Gerrit's link. A problem: the reply says sorry and that Gerrit will call, Gerrit gets the note and a
   to-do, and this customer never gets a review or referral ask. No answer in 7 days: no review ask.
3. A week after the review ask: a referral ask, with Gerrit's reward words if he saved them.
4. About 6 months after the install: an "other rooms" check-in (in spring, the patio too).

Only known customers get texts (a Salesforce match, a customer file or the quote follow-ups). Never text a number
you found only in a Completed email.

## When Gerrit gives you his review link or referral reward
- Review link: `zingas-installs set review-link "https://..."`. Send him what it prints.
- Referral reward: `zingas-installs set referral "a $50 gift card"` will be refused: texts never carry an amount.
  Use his words without the number ("a gift card as a thank-you"), and tell him why. To remove it:
  `zingas-installs set referral ""`.
- `zingas-installs settings` shows both. `zingas-installs status` counts the installs.

## When Gerrit asks about installs
`zingas-installs status` for the counts. When he says who a Completed email in the brief is about, start it:
`zingas-installs add --phone "<their number>" --installed YYYY-MM-DD` (the date of the Completed email), and send
him what it prints. It only works for a customer Val knows.
Never change `installs/state.json` by hand.
