# Changelog

This library follows [semantic versioning](https://semver.org): a breaking
change to a workflow's input type, a connector, or a context variable bumps
the major version. Each release is a git tag `vX.Y.Z`.

## 1.0.0

First release. Requires Orqen >= 0.10.0.

- Workflows: Support auto-reply, Transactional notification, Inbox triage digest.
- Missions: Support inbox webhook, Transactional email API, Weekday inbox digest.
- Connectors: Email toolkit, CRM API. Credentials: Email toolkit key, CRM token.
- Context: Email local. Types: Inbound email, Transactional email.
- Skills: Brand voice, Support reply writer, Email triage.
- Offline tests, including JSON rendering of every request template with hostile input.
