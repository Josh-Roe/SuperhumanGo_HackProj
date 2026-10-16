# Event workspace · Member 1

The site opens directly to **Your events**. The sidebar has Your events, Settings, and Profile. Click an event or the plus button to use the three steps: event details → design/inclusion → distribution. Signup/login is skipped at the user's request.

```sh
npm ci
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
npm run lint
npm test
npm run build
```

Share Vite's Network URL with teammates on the same Wi-Fi. Keep the host awake and the process running. The current workspace is an explicitly labeled **local preview**: sample data and profile edits exist only in each browser tab. Reload resets them. It cannot publish or send invitations. No account authentication or private backend access is bypassed.

## Superhuman Go handoff

Settings and the design step open [Superhuman Go](https://go.superhuman.com/) in another tab. The organizer adds the team's custom MCP connector in Go and authorizes its tools. They then prompt Go to save event details, Canva artifacts, prose, and distribution preparation into the canonical website records. Return to the event and refresh to review actual results once integration is connected.

Set `VITE_PUBLIC_MCP_URL` to the public hosted HTTPS connector address supplied by Member 3. Without it, the UI clearly says setup is pending. No localhost URL, auth token, fabricated install deep link, or automatic connection success is substituted. The UI supplies a copyable event-ID/revision prompt, with a manual-copy fallback on HTTP LAN pages where Clipboard access is unavailable. Opening Go does not transmit the prompt or install anything automatically. See [official connector help](https://support.grammarly.com/hc/en-us/articles/40642362241293-About-Superhuman-Go-agents-and-connectors).

The Go handoff is implemented; the actual custom MCP and backend/provider round trip still belong to Members 2–4. Current sample events do not synchronize with Go. Canva/Gmail/Calendar connection rows are labeled unverified. Organizer review and send confirmation remain required.

## Integration boundary

`src/types.ts` and `src/api.ts` preserve the proposed normalized REST gateway, runtime validation, authenticated writes, expected revisions, and stable publish idempotency keys. The current simplified shell intentionally uses only the in-memory preview gateway while sign-in is skipped. Auth utilities remain available for the future accepted account flow; environment flags alone do not activate live mode in this shell.

Member 2 must accept/normalize `GET /api/events` → `EventRecord[]`, event read/mutation responses → `WorkspaceEvent`, and authenticated create/PATCH/prepare/review/publish/sync endpoints. Member 3's `/api/dev` shape differs and must not be treated as production Supabase data. Private records, trusted Go provenance, exact asset/approval revisions, ownership/RLS, and idempotency must be validated server-side. Public browser config must never include connector tokens, OAuth secrets, or service-role keys.

Canva previews render actual HTTPS metadata when supplied. Unknown inclusion facts remain unknown; sourced yes/no facts require confirmation dates. Access/sensory details and prose previews are collapsed to keep the main flow small. Provider status and private guest responses are expandable sections inside distribution. Sent email/attachments remain immutable; sent invitations require a new change notice, while unsent drafts are replaced. Exact Canva transaction digest approval and public event links remain pending backend handoffs.

Checks cover direct entry, the three sidebar links/stages, event creation, Go links/prompts/setup-pending states, writing provenance/review gates, inclusion sources, provider errors, private RSVP evidence, local profile editing, auth/REST boundary errors, revision conflicts, and timezone/DST conversion. Desktop/mobile browser and full screen-reader verification for this revision remain separate checks.

## Free-form requests in standalone Go

The intended pipeline is **user describes the event in Go → Go calls typed MCP tools → backend validates/stores canonical records → website renders the structured snapshot**. Users do not need headings, keywords, JSON, or a fixed order. Go asks about missing dates/timezones and ambiguous instructions before committing those facts. The website routes by explicit record fields and content kinds; words inside a body never overwrite event fields.

`src/content.ts` covers all current Member 3 content kinds. `summary` and `document` are normalized aliases; flyer brief/copy/alt text, email subjects, documents and optional Notion notes are preserved. Unsupported kinds and duplicate content IDs fail visibly instead of being discarded. `parseWorkspace` also normalizes Member 4's `flyer_png`/`event_document` and `review_state` metadata. Hash-derived artifact IDs are UI keys only; preview URLs are never invented. Different event IDs are rejected. Actual signed links and provider receipts must come from the authenticated server.

| Structured output                                                 | Website destination   |
| ----------------------------------------------------------------- | --------------------- |
| Canonical title, location, times, timezone, invitees              | Event details         |
| `description`                                                     | Event details writing |
| `flyer_brief`, `flyer_copy`, `flyer_alt_text`                     | Canva design          |
| `summary` / `plain_language_summary` and inclusion facts/findings | Inclusion             |
| `document` / `event_document`, `notion_note`                      | Documents             |
| `invitation`, `change_notice`, subject, Gmail/Calendar receipts   | Distribution          |

`App` accepts an `eventGateway` composition prop for an already-authenticated backend adapter; it defaults to the public local preview. Refresh loads list/detail snapshots from that gateway. This composition seam and mocked typed-output tests are not a live Go transfer or natural-language understanding test. Automatic push/subscription refresh remains pending the shared backend contract.

Missing server work: owner-scoped create/update event MCP tools, durable canonical storage, artifact recording, accepted organizer read/review/approval APIs, scoped browser identity without a signup gate, and a real standalone Go round trip. Member 3's current branch exposes read/queue/save-content tools, but not event create/update tools. See Member 1 context for the exact handoff.
