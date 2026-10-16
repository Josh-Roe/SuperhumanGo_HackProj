# Organizer frontend · Member 1

React/TypeScript organizer screens for events created by Superhuman Go through the website’s MCP tools, with manual creation/editing preserved. The product name remains undecided.

```sh
npm ci
npm run dev
npm run lint
npm test
npm run build
```

Open Vite’s local URL and choose **Open local preview**. Sample writing and provider receipts are synthetic and visibly labeled. Changes exist only in memory; leaving preview or reloading resets them. Preview cannot publish, send, or connect accounts. No automatic Go responses are simulated.

## Integration boundary

`src/types.ts` defines the **proposed**, normalized UI contract. `src/api.ts` isolates HTTP/auth. The event REST API has not been accepted or implemented on the baseline branch; do not enable it until Member 2 connects and verifies these shapes. Member 3's `/api/dev` workflow response is a different shape and is intentionally not treated as production Supabase data.

Copy `.env.example` to `.env` and configure only public settings after agreement:

- `VITE_EVENT_API_ENABLED=true`
- `VITE_SUPABASE_URL` (HTTPS project origin)
- `VITE_SUPABASE_PUBLISHABLE_KEY` (public browser key, never service-role)
- `BACKEND_PROXY_TARGET` (development Vite proxy only)

Sign-in uses the [Supabase password grant](https://supabase.github.io/auth/). Its access token is held in React memory and sent as `Authorization: Bearer` to same-origin `/api/events` requests. The session ends at expiry or local sign-out; no tokens are persisted or logged. Refresh, registration, password recovery, Google/Canva account-connect routes, and global Supabase session revocation remain future auth-owner handoffs. Local sign-out drops this tab’s session. Secrets and connector tokens never belong in browser environment settings.

The adapter expects `GET /api/events` → `EventRecord[]`; `GET /api/events/{id}` and mutation responses → `WorkspaceEvent`. `POST /api/events` creates; `PATCH /api/events/{id}` includes `expected_revision`; `/prepare`, `/review`, `/publish`, `/sync` use POST and expected revision. Review carries content edits, facts, and acknowledgment. Publish/update carries a stable idempotency key in JSON and `Idempotency-Key`. The server must revalidate content IDs/provenance, ownership, review/approval, current artifacts, revision, and recipients before any side effect. Client gating is UX only.

Go MCP event-creation tools belong to Member 3, durable task/event state and organizer REST/auth to Member 2. The frontend does not implement a second MCP server or an invented Go chat API. Refresh reloads API-backed Go-created events; push/realtime delivery is pending a contract. Artifact preview/edit/current links accept HTTPS only. Document prose is displayed as text; no untrusted HTML is injected.

Review includes source/date fields and unresolved inclusion facts. Live Canva transaction approval still needs the operation/digest/revision endpoint from Members 2–4; the generic review button does not commit Canva transactions. Provider state and receipts stay distinct from event phase. Stale output is visible and cannot be approved for the current revision. Missing artifacts prevent publishing. Existing sent mail is immutable and requires a change notice. Unsent drafts are labeled as replacements.

All previews require organizer authentication in live mode; there is no public event route until the backend supplies a separately approved public schema/link policy. Private RSVP source evidence is organizer-only. No attendee-sensitive fixtures or credentials are committed.

## Same-Wi-Fi preview

```sh
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

Share the Network URL printed by Vite with teammates on the same Wi-Fi. Keep the host awake and the process running. Each browser has separate, ephemeral sample data. Guest Wi-Fi client isolation or the host firewall can block access even when the host responds locally. This is a LAN development preview, not a production deployment.
