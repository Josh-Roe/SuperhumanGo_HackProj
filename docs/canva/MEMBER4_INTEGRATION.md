# Custom Canva flyers and Go-written documents

Owner: Member 4. Updated 2026-10-16. Branch: `codex/member-4-canva-inclusion`.
These are implemented service interfaces and proposed cross-member bindings, not registered HTTP endpoints.

## Accepted direction

The team lead clarified on 2026-10-16: **no template; make each flyer custom to its event using Canva MCP.**
The primary route is Superhuman Go's event-specific brief → Canva MCP `create-design` → organizer review → verified export → private Supabase Storage. No Brand Template is required. Canva produces the layout; Superhuman Go supplies the event prose. Never describe Canva-generated additional wording as Go-written; remove or send it through Go before approval.

## Evidence ledger

| Capability | Actual evidence in this task |
| --- | --- |
| Connected Canva account read access | Live design search and rich-text read succeeded on 2026-10-16. No private design content copied into Git. |
| Autofill templates | Live search returned zero autofill-ready templates; an existing flyer had an empty field dataset. This route is superseded by the user's custom-design decision. |
| Custom creation | Official tool/schema inspected; synthetic responses tested. No live generation or AI-credit/plan entitlement test. |
| Editing / same-design update | Transaction, element mapping, approval, read-back and stale-copy checks tested with synthetic responses. No live mutation. |
| Export | Adapter and bounded download tests pass locally. `export-design` is documented in remote Canva MCP but is absent from this chat's exposed connector tools. A host must verify it is granted; do not claim current chat export works. |
| Go prose | Strict producer/kind/revision contracts and queue handoff implemented. No live Go output in these tests. |
| Storage | Immutable paths, hash receipts and revision-CAS contract tested against a double. Supabase implementation/RLS belongs to Member 2. |

Official references: [custom creation](https://www.canva.dev/docs/apps/mcp/tools/create-design/), [editing transactions](https://www.canva.dev/docs/apps/mcp/tools/start-editing-transaction/), [read-back](https://www.canva.dev/docs/apps/mcp/tools/get-design-content/), [export](https://www.canva.dev/docs/apps/mcp/tools/export-design/), [MCP tools](https://www.canva.dev/docs/apps/mcp/tools/). Tool availability in a connected chat does not install credentials or authorize a backend session.

## Member 3: Go request and Canva execution

Python modules are under `backend/src/hackathon_backend/`:

| Module | Interface |
| --- | --- |
| `services/assets/requests.py` | `await request_event_prose(event, queue, owner_id=principal.owner_id)` |
| `services/assets/models.py` | `EventSnapshot`, `GoContent`, `DesignRef`, `Approval`, `AssetRecord` |
| `providers/canva/__init__.py` | `CanvaMCPAdapter(session, owner_id=principal.owner_id, tool_names=...)` |
| `services/assets/documents.py` | `render_event_document(event, document, owner_id=..., summary=...) -> bytes` |
| `services/assets/storage.py` | `AssetService(storage)`, `ExportDownloader(dedicated_http_client)` |

`GoPreparationQueue.enqueue(ProseRequest)` must atomically validate owner/current revision and deduplicate `owner:event:rN:go:asset-prose-v1`. It returns `ProseQueueReceipt` with operation ID and `queued` or `awaiting_go`; a receipt never means prose exists. The batch requests `flyer_brief`, `flyer_copy`, `event_document`, `plain_language_summary`, `flyer_alt_text`. Regenerate all five for each new revision. Member 3 should incorporate these names into its trusted content repository and approved Go tools. There is no fallback completion call.

`GoContent` includes owner/event/revision, `producer="superhuman_go"`, generation ID, kind, body, language and organizer-review boolean. Load it from a trusted server repository after an authenticated Go write. A browser-supplied producer label is not evidence of Go provenance. `flyer_brief` describes design direction and approved wording; `flyer_copy` is only the displayed description, without design instructions. Any new wording introduced during Canva editing goes back through Go. User changes to canonical event facts do not need an LLM to be rendered exactly.

Workflow:

1. Claim a durable operation for the authorized owner/event/revision; hold a per-design write lock through an edit. Fetch the canonical current revision before every side effect. This adapter validates supplied snapshots; it cannot query the database itself.
2. `create_flyer(event, brief)` starts `create-design` with Portrait A4 and exact title/time/location appended to the Go brief. Persist the job ID and **server-only latest continuation token**. The token is excluded from `model_dump`; encrypt/persist it explicitly in Member 2's job secret storage, never the public operation DTO.
3. When no Canva widget is doing the polling, call `poll_creation` after `next_poll_at`, use the returned newest token, and relay `polling_instructions`. With Canva's own widget, let the widget poll. Do not run two pollers. Surface quota/moderation/admin/invalid-input failures without blind retries.
4. Completed job returns `DesignRef`; use the returned view link. If Canva supplies no separate editor link, `edit_url` falls back to the supplied design link. Open it for organizer edits. Check text with `verify_text(event, design, event.flyer_fields())`; `verified` means text was found, **not** a visual/accessibility audit. An organizer must inspect the layout, all prose, clipping, contrast and factual consistency. Record that review in the trusted repository before distribution.
5. For a newer event revision, use `ElementMapping(role, element_id, previous_text)` for separate title/when/location elements; optional description uses Go `flyer_copy`. Obtain IDs from the actual editing transaction output, never fabricate them from role names. `stage_update` validates current page-1 elements and prior text, stages replacements and returns an `EditPreview` with thumbnails, old/new text and digest. Combined text, changed IDs, image-only text or multiple pages require manual review/remapping. The adapter does not silently overwrite a changed layout.
6. Display that exact preview and changed fields. Canva's commit tool explicitly requires preview plus user approval. Save `Approval` from the authenticated organizer action, bound to its digest/revision/time; never create an approval automatically. `commit_update` commits the transaction, then reads text back and detects mapped stale values. Cancel abandoned transactions using the session's cancel tool. Operation locks/leases and preview expiry/reconciliation belong to the coordinator.
7. Read-back success returns the same design ID at the new revision; failures remain `needs_review`. Rasterized/unmapped stale details and visual clipping require organizer inspection. If a fresh custom design is needed, run an explicit new creation and retain the prior binding/history.
8. `export_png(event, verified_design)` accepts a completed, single-page PNG export. Pending/failed/multipage export returns `export_not_ready_or_not_single_page`; the host reconciles the returned provider operation rather than pretending completion. Export once under a durable operation claim. Download immediately with `ExportDownloader.png`, then `AssetService.save_flyer` with actual export ID and Go alt text. Signed CDN URLs are transient server data, not durable preview links. Header/dimension validation is not a full image decoder or visual audit.
9. `AssetService.save_document` renders escaped Go document/summary prose into semantic HTML and stores it through the same revisioned interface. It does not synthesize missing text. Serve unreviewed content privately. A new revision must regenerate prose and rerun review.

The session implements `await call_tool(name, arguments)`. Official remote names are hyphenated. A connector host can map them to its own tool identifiers via `tool_names`. Required tools: `create-design`, `get-create-design-async-job`, `get-design-content`, `start-editing-transaction`, `perform-editing-operations`, `commit-editing-transaction`, `cancel-editing-transaction`, `export-design`. Check the actual session's `list_tools`/grants at startup. The protocol is an injectable executor, not an HTTP Canva connection or OAuth callback. Member 3 owns session hosting/auth and route/tool registration in `main.py`.

Never retry an uncertain create/commit automatically; persist IDs and reconcile. Errors are sanitized machine codes. Translate owner failures to `forbidden`, stale snapshots to `revision_conflict`/`superseded`, unavailable tools/grants to `integration_not_connected`, pending Go to `awaiting_go`, and provider failures to `provider_failed`. Keep operation IDs and retry/review actions visible.

## Member 2: exact Storage requirements

Implement `AssetStorage` in the owned repositories, with authenticated owner scope:

```python
async def assert_current(owner_id: str, event_id: str, revision: int) -> None: ...
async def put_if_absent(object_key: str, content: bytes, content_type: str,
                        sha256: str) -> StorageReceipt: ...
async def publish_current(record: AssetRecord, *, expected_revision: int) -> None: ...
```

- Private bucket. Path: `{owner}/events/{event}/r{revision}/{kind}/{sha256}.html|png`. MIME types: `text/html; charset=utf-8`, `image/png`. Maximum 10 MB each. Permit organizer-scoped writes only; do not rely solely on this path prefix as authorization.
- `put_if_absent` is immutable/idempotent, verifies existing bytes/hash on conflict, returns key/hash/byte count. Never overwrite previous exports.
- `publish_current` atomically checks owner AND canonical event revision and writes artifact metadata/current pointer. Raise `StaleRevisionError` on a race. Publishing an asset pointer is internal metadata, not authorization to send invitations or publish a public event. An orphan upload after a CAS failure must not become current; cleanup can be deferred.
- Metadata includes event/revision/kind, object key/hash/bytes/MIME, timestamps, Go content generation ID, review state, Canva design/export IDs and design-brief/copy generation ID (`canva_generation_id`). Store Go alt text/summary relationships using their generation IDs. Resolve the actual alt-text body from trusted content records when building the UI.
- Provide stable application current links resolved through current revision, with authorization/explicit public-event policy and short-lived signed object URLs. Public links must exclude private inclusion/RSVP sources. Old emails/attachments remain snapshots; link to current material and send a new approved notification.
- Storage ACL/RLS/live import/current-link endpoints are not implemented here. Confirm these contracts before registering public routes. No shared config, migration, lockfile or `main.py` change is made by Member 4.

## Member 1: frontend metadata and review UI

`AssetRecord.preview_metadata()` returns `event_id`, `event_revision`, `kind`, `content_type`, `sha256`, `byte_length`, `canva_design_id`, `review_state`. Join with a backend-authorized preview/current URL and Go alt text, not a Canva CDN download URL. Display revision, review state and per-operation status. For flyers add `DesignRef.edit_url`/`view_url` for the authorized organizer. Open Canva for free editing; reconcile and rerun text/visual review after edits.

`EditPreview` is server state. The UI should receive only operation ID, digest, event revision, mapped old/new values and approved preview URLs; keep the transaction handle server-side. Show the actual preview, a review button tied to that operation/digest, and separate `Update`/`Publish` actions. A newer event invalidates this review. Never let the browser construct `VerifiedDesign`, `Approval`, or provenance records as trusted facts.

Use [generated JSON schemas](member4.schemas.json) for adapter types while Member 2 freezes the canonical API. These are Member 4 proposals and do not replace `INTEGRATION_CONTRACT.md`. All inclusion findings are organizer-private; see [inclusion contract](../inclusion/CONTRACT.md).
