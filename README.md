# orqen-email-workflows

Production email workflows for [Orqen](https://github.com/momen-suleman) Studio,
delivered as an **Orqen Library**: import this repository from the Library page
and you get connectors, credentials, an env context, input types, AI skills,
three workflows and three missions, all wired together.

Email delivery goes through
[email-toolkit](https://github.com/momen-suleman/email-toolkit) over its REST API
(`POST /executions`), behind an authenticated **connector**. That gives you real
HTTP status codes, a bearer key resolved per environment, and the toolkit's
idempotency, so a retried or re-delivered message is never sent twice.

Requires Orqen **0.10** or later (input sources, connectors, branches, error
policies, `flow.*` and `data.*` nodes).

## What you get

| Kind | Item | Purpose |
|---|---|---|
| Workflow | **Support auto-reply** | Validate → enrich (CRM) → route → AI draft → policy preflight → send reply, or escalate to the team |
| Workflow | **Transactional notification** | Validate → send a template email once per idempotency key → structured failure report |
| Workflow | **Inbox triage digest** | Fetch unread mail → AI summary by urgency → one digest per day |
| Mission | Support inbox webhook | `POST /api/hooks/<id>` runs Support auto-reply for each inbound email |
| Mission | Transactional email API | `POST /api/hooks/<id>` sends one notification |
| Mission | Weekday inbox digest | 08:00 UTC Mon–Fri (installed **disabled** until IMAP is set up) |
| Connector | Email toolkit | `http://127.0.0.1:9333`, credential *Email toolkit key* |
| Connector | CRM API | `https://crm.example.com/api` (placeholder), credential *CRM token* |
| Credential | Email toolkit key / CRM token | Bearer secrets that reference `{{ ctx.EMAIL_TOOLKIT_API_KEY }}` / `{{ ctx.CRM_API_TOKEN }}` |
| Context | Email local (env) | Addresses, feature flags and the two secrets |
| Types | Inbound email, Transactional email | Validated trigger input |
| Skills | Brand voice, Support reply writer, Email triage | Stacked in order on the AI nodes |

## Set up

1. **Run email-toolkit with a key** on port 9333 (console provider by default, so nothing is really sent):

   ```bash
   docker run -p 9333:9321 -v email-toolkit-data:/app/data \
     -e EMAIL_TOOLKIT_API_KEY=<a long random key> email-toolkit
   ```

   For real delivery add `SMTP_HOST`, `SMTP_USERNAME` and `SMTP_PASSWORD_FILE`. For the digest add the `IMAP_*` settings (see the toolkit README).

2. **Import the library.** In Orqen Studio open **Library**, enter `momen-suleman/orqen-email-workflows`, then **Scan** and **Import**.
   While you are developing it locally you can import the working folder instead:

   ```powershell
   orqen library import C:\Projects\Momen\orqen-email-workflows
   ```

3. **Fill in the context.** Open **Contexts → Email local** and set:
   - `EMAIL_TOOLKIT_API_KEY` (secret): the same key you gave the toolkit
   - `SUPPORT_FROM`, `SUPPORT_TEAM_EMAIL`, `NOTIFY_FROM` and `DIGEST_TO`: real addresses (they must be allowed by the toolkit's sender policy)
   - optional: `CRM_ENABLED=true` and `CRM_API_TOKEN`, then edit the **CRM API** connector's base URL
   - optional: `EMAIL_AUDIT_LOG=true` to keep an audit trail in the context database (provision the database first)

4. **Check the connection.** On **Connectors → Email toolkit**, with *Email local* selected in the top bar, send a test GET to `/health`.

5. **Get a webhook token.** On **Workflows → Missions**, press **New token** on *Support inbox webhook*. The token is shown once:

   ```bash
   curl -X POST http://127.0.0.1:8787/api/hooks/mission.custom.support-inbox-webhook \
     --data-urlencode "token=<token>" \
     --data-urlencode "document@examples/inbound-email.json"
   ```

Re-importing the library syncs it: everything it installed is replaced, so
secret values and local edits have to be entered again. Keep production
values in a separate context (e.g. copy *Email local* to *Email production*).

## How the support workflow handles each case

```
trigger ─▶ intake (validate) ─┬─▶ crm lookup (run if CRM_ENABLED, retry ×2, continue on error)
                              │
                              ├─▶ route (switch) ──case auto-reply──▶ draft (AI, skills: brand voice → reply writer,
                              │        │                                      retry ×1, fallback text)
                              │        │                               ─▶ message (compose JSON)
                              │        │                               ─▶ preflight (toolkit validate, retry ×2)
                              │        │                               ─▶ checks (if valid) ──true──▶ send reply (retry ×2, 409 = already sent)
                              │        └──case escalate─────────────┐              └──false─┐         │ failure
                              │                                     ▼                       ▼         ▼
                              │                               notify-team (wait for ANY incoming branch)
                              │                                     │ always            ┌───────────┘ always
                              │                                     ▼                   ▼
                              │                               audit (context DB, run if EMAIL_AUDIT_LOG)
                              └──failure──▶ reject (structured report)
```

| Scenario | What happens | Run status |
|---|---|---|
| Normal question | Reply drafted, preflighted and sent as a threaded `Re:` reply | Succeeded |
| Subject says "urgent", body mentions a refund or a lawyer, or CRM tier is VIP | No auto-reply; the team gets a `[Needs attention]` email with the original message | Succeeded |
| Invalid input (bad sender, empty body…) | Every violation listed in the `reject` report; nothing is sent | Degraded |
| Recipient suppressed or the sender not allowed by policy | Preflight blocks the reply; the team is notified with the violations | Succeeded |
| AI provider down | The fallback holding reply is sent | Degraded |
| Toolkit unreachable or returning 5xx | Retried with backoff; then the team is notified (if reachable) | Degraded / Failed |
| Same message delivered twice | The idempotency key `reply-<message_id>` stops a second send (HTTP 409 is accepted as "already sent") | Succeeded |
| No env context selected | Fails at *Compose reply*: `{{ ctx.SUPPORT_FROM }} has no value` | Failed |

Client errors (4xx) are never retried: only timeouts, connection failures,
429/408/425 and 5xx responses are. The workflow uses the *handled* status
policy, so a failure caught by a failure branch ends **Degraded** instead of
**Failed**.

## Input formats

**Inbound email** (`types/inbound-email.json`):

```json
{"message_id": "<CAF1234@mail.example.org>", "from": "ada@example.org", "from_name": "Ada",
 "subject": "Cannot download my invoice", "body": "Hi, the invoice for order 1042 …"}
```

**Transactional email** (`types/transactional-email.json`):

```json
{"to": "ada@example.org", "template_id": "welcome", "variables": {"name": "Ada"},
 "idempotency_key": "signup-ada-2026-11-14"}
```

Use one `idempotency_key` per business event. Sending the same event again
returns the original execution instead of a second email.

## Develop and test

```bash
python -m unittest discover -s tests -v
```

The tests run offline. They check every `@reference`, branch name and
retry/failure path, check that no literal secret is committed, and render
every JSON request template with hostile sample input (quotes, newlines,
braces) to prove it still produces valid JSON. CI runs them on every push.

Layout:

```
orqen.json        manifest
connectors/       reusable HTTP endpoints        credentials/  write-only secrets (context references only)
contexts/         env variables (no secret values)
types/            trigger input schemas          skills/       AI instructions (Markdown)
workflows/        Canvas graphs                  missions/     triggers: webhook, daily schedule
examples/         sample inputs (not imported)   tests/        offline validation
```
