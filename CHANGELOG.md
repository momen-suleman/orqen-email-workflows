# Changelog

This library follows [semantic versioning](https://semver.org): a breaking
change to a workflow's input type, a connector, or a context variable bumps
the major version. Each release is a git tag `vX.Y.Z`.

## 1.2.0

- **Inbox intelligence poll** mission: every 5 minutes, runs Email Inbox Intelligence once for each unread message not processed before (up to 10 per poll), through a mission `feed` on the email-toolkit connector. Installed disabled. Needs an Orqen build with mission feeds; older builds install it as a plain scheduled mission that has no input.
- Tests: feeds must reference a known connector, be scheduled and install disabled.

## 1.1.0

- **Email Inbox Intelligence** workflow and **Inbox intelligence webhook** mission, composed from Orqen's `mail.*` nodes: fetch by IMAP UID, parse, metadata, content, security indicators, rule classification, guarded action plan, apply. No AI node.
- Manifest declares `packages` (`mail.mime`, `mail.rules`, `mail.mailbox`). Requires an Orqen build that ships them (after 0.10.0) and an email-toolkit with `mailbox.get_raw` and `mailbox.apply`.
- New context variable `MAIL_MODE` (`dry-run`). Mailbox writes need `MAIL_MODE=apply`, an allow-listed action, enough confidence and a toolkit key with `email.mailbox.write`.
- Tests: mutation guards, package requirements, the 400-character description limit.

## 1.0.0

First release. Requires Orqen >= 0.10.0.

- Workflows: Support auto-reply, Transactional notification, Inbox triage digest.
- Missions: Support inbox webhook, Transactional email API, Weekday inbox digest.
- Connectors: Email toolkit, CRM API. Credentials: Email toolkit key, CRM token.
- Context: Email local. Types: Inbound email, Transactional email.
- Skills: Brand voice, Support reply writer, Email triage.
- Offline tests, including JSON rendering of every request template with hostile input.
