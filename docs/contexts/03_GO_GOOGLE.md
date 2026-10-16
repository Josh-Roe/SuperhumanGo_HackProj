# Member 3 context: Superhuman Go, Google, synchronization, RSVP

Owner: Member 3 (human name/GitHub pending). Updated 2026-10-16. Status: **assigned; product integration not started by this handoff**.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), [all four member contexts](../TEAM_TASKS.md), and [contract](../INTEGRATION_CONTRACT.md) before work. Write only this personal context. [Copy-ready prompt](../prompts/03_GO_GOOGLE.md).

## Scope

Own official Go connector/agent instructions, authenticated event MCP tools, `workflows/**`, Google provider adapters, Google account connection, sync/update jobs, email-reply RSVP handling, `main.py` composition, and Go integration docs. Coordinate shared dependencies/config with 2 and Canva/inclusion calls with 4.

## First deliverables

1. Prove Go reads an authorized test event and saves Go-written output through the hosted MCP connector. Verify actual account grants/triggers. Keep a visible manual Go-assisted queue fallback if website-triggered automation cannot be supported.
2. Make Go produce descriptions, plain-language summaries, invitation/change emails, document prose, and optional Notion notes; document a real Grammarly writing-assistance path. Gemini support must be explicitly labeled.
3. Implement one-writer Calendar/Gmail operations: stable event ID; deliberate notifications; stable draft tracking; new message/draft after sent; current flyer/document links and MIME attachments; operation receipts/idempotency.
4. Sync Calendar RSVP status and classify matched reply emails through Go. Ambiguous/forwarded/quoted/conditional replies require review; preserve source/provenance and prevent duplicate ingestion.

## Dependencies and handoffs

- Need from 2: authenticated principal, tenant-scoped repository/vault methods, event revisions, queue/approval/idempotency APIs and RSVP persistence.
- Need from 4: Canva/inclusion/document callable adapters and current revisioned artifact results.
- Supply to 1: Go execution status, provider operation status/receipts, links, RSVP state, and connection errors. Register 2/4 routers through the agreed composition point in `main.py`.

## Decisions and progress

- Agreed from user: Superhuman Go and Grammarly power writing/coordination; Gmail, Calendar and reply-based RSVP are core.
- Supported route verified in documentation: Go calls a hosted Streamable HTTP MCP connector; no general backend Go completion endpoint has been established.
- Open: native Go Google connectors vs backend OAuth tools; pick and document one executor per operation to avoid double writes. A shared global MCP token is not organizer authorization.
- Verification: starter Pack validation is historical; no live product generation, Google write, trigger, or RSVP ingestion is proven yet.
- Blockers: eligible Go/account access, hosted URL, scoped identity, Google OAuth/grants, first event repository contract.
- Next action: Go → scoped test event → save generated content proof, then publish tool/trigger/provider execution decisions here.

## Update format

`Date | branch/commit/PR | status | capability/decision/source | tool/provider contracts | local vs mocked vs live evidence | blocker | next owner/action`. Never claim a scheduled/manual fallback is real-time website automation, or a draft is a sent message.
