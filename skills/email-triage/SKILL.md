---
name: Email triage
description: Summarize a batch of unread emails into a prioritized digest.
---
You receive a JSON list of unread messages (sender, subject, date, snippet).

Produce a plain-text digest:
1. "Needs action today" — messages that are urgent, from customers waiting on us, or mention money, outages or security.
2. "This week" — normal requests.
3. "FYI / can wait" — newsletters, notifications, automated mail.

One line per message: sender — subject — the action needed (max 15 words).
End with a one-line count per section. If the list is empty, say "Inbox zero — nothing unread."
