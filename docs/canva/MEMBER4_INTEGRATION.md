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
| Custom creation | User-authorized fictional sample created through this chat's Canva MCP; full metadata links and text read back. Adapter normalizes observed `canva.link` completions through `get-design` by ID. No live Go generation or native Python OAuth session is claimed. |
| Editing / same-design update | Live sample exposed 15 editable text elements in a transaction, then inspection was cancelled without edits. Replacement/approval/commit/read-back/stale-copy behavior is locally tested with synthetic responses; no live edit commit. |
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
| `providers/canva/session.py` | `connect_canva`, `DiscoveredCanvaSession.discover`, `capabilities`, owner-bound `adapter` |
| `services/assets/documents.py` | `render_event_document(event, document, owner_id=..., summary=...) -> bytes` |
| `services/assets/storage.py` | `AssetService(storage)`, `ExportDownloader(dedicated_http_client)` |
| `services/assets/attachments.py` | `RevisionedAttachmentSource` conforms to Member 3's actual `AttachmentSource` port |
| `services/assets/supabase_read.py` | `SupabaseAttachmentRepository` wraps Member 2's published Storage without modifying it |

`GoPreparationQueue.enqueue(ProseRequest)` must atomically validate owner/current revision and deduplicate `owner:event:rN:go:asset-prose-v1`. It returns `ProseQueueReceipt` with operation ID and `queued` or `awaiting_go`; a receipt never means prose exists. The batch requests `flyer_brief`, `flyer_copy`, `event_document`, `plain_language_summary`, `flyer_alt_text`. Regenerate all five for each new revision. Member 3 should incorporate these names into its trusted content repository and approved Go tools. There is no fallback completion call.

`GoContent` includes owner/event/revision, `producer="superhuman_go"`, generation ID, kind, body, language and organizer-review boolean. Load it from a trusted server repository after an authenticated Go write. A browser-supplied producer label is not evidence of Go provenance. `flyer_brief` describes design direction and approved wording; `flyer_copy` is only the displayed description, without design instructions. Any new wording introduced during Canva editing goes back through Go. User changes to canonical event facts do not need an LLM to be rendered exactly.

Workflow:

1. Claim a durable operation for the authorized owner/event/revision; hold a per-design write lock through an edit. Fetch the canonical current revision before every side effect. This adapter validates supplied snapshots; it cannot query the database itself.
2. `create_flyer(event, brief)` starts `create-design` with Portrait A4 and exact title/time/location appended to the Go brief. Persist the job ID and **server-only latest continuation token**. The token is excluded from `model_dump`; encrypt/persist it explicitly in Member 2's job secret storage, never the public operation DTO.
3. When no Canva widget is doing the polling, call `poll_creation` after `next_poll_at`, use the returned newest token, and relay `polling_instructions`. With Canva's own widget, let the widget poll. Do not run two pollers. Surface quota/moderation/admin/invalid-input failures without blind retries.
4. Completed job returns `DesignRef`. `canva.link` completions trigger `get-design` by the actual returned ID; metadata must match that ID and contain full HTTPS Canva links. No HTTP shortlink redirects or arbitrary URLs are followed. If a full link has no separate editor link, `edit_url` falls back to it. Open for organizer edits. `preview_flyer(event, design)` verifies canonical text and returns a one-page `FlyerReviewPreview`, bound to the provider timestamp and thumbnail. Show its actual thumbnail and all prose for visual/accuracy review. From a trusted organizer action call `approve_flyer(event, preview, approval)`; it checks the exact digest, revision, provider timestamp and text again, without changing Canva. `verified` alone means text was found, **not** a visual/accessibility audit. Persist the approved result before distribution. Provider timestamps are an available change signal, not a provider-side atomic compare-and-set; keep write locks and reconcile concurrent manual edits.
5. For a newer event revision, use `ElementMapping(role, element_id, previous_text)` for separate title/when/location elements; optional description uses Go `flyer_copy`. Obtain IDs from the actual editing transaction output, never fabricate them from role names. `stage_update` validates current page-1 elements and prior text, stages replacements and returns an `EditPreview` with thumbnails, old/new text and digest. Combined text, changed IDs, image-only text or multiple pages require manual review/remapping. The adapter does not silently overwrite a changed layout.
6. Every editing operation must report success for its mapped element, and a valid Canva thumbnail must be available. Display that exact preview and changed fields. Canva's commit tool explicitly requires preview plus user approval. Save `Approval` from the authenticated organizer action, bound to its digest/revision/time; never create an approval automatically. The digest includes the thumbnail URLs as well as transaction/fields. `commit_update` commits the transaction, then reads text back and detects mapped stale values. `cancel_update(event, preview)` discards abandoned/superseded previews without commit. Operation locks/leases and preview expiry/reconciliation belong to the coordinator.
7. Read-back success returns the same design ID at the new revision; failures remain `needs_review`. Rasterized/unmapped stale details and visual clipping require organizer inspection. If a fresh custom design is needed, run an explicit new creation and retain the prior binding/history.
8. Prefer `request_png_export(event, verified_design)`: it preserves the actual export ID in a typed `ExportReceipt` with `pending`, `completed`, or `failed` state. Signed `download_url` is server-only and excluded from serialization/repr. Pending exports are not automatically reissued or polled via an invented status API; use the actual host's supported reconciliation path. `export_png` remains a compatibility helper for callers requiring completed results. Reject multipage/untrusted download URLs. Download completed output immediately with `ExportDownloader.png`, then `AssetService.save_flyer` with actual export ID and Go alt text. Signed CDN URLs are transient server data, not durable preview links. Header/dimension validation is not a full image decoder or visual audit.
9. `AssetService.save_document` renders escaped Go document/summary prose into semantic HTML and stores it through the same revisioned interface. It does not synthesize missing text. Serve unreviewed content privately. A new revision must regenerate prose and rerun review.

The session implements `await call_tool(name, arguments)`. Official remote names are hyphenated. `DiscoveredCanvaSession.discover` pages through the actual `list_tools` inventory and maps canonical names, underscore names, or this chat connector's namespaced names. Ambiguous aliases/pagination loops fail closed. `capabilities()` reports available create/review/edit/export groups and exact missing tools; absent export is explicit. `get-design` is now required for creation normalization and initial review. Both the session factory and adapter reject cross-owner reuse. Member 3 owns hosting/auth/route registration; Member 4 supplies the executable connection factory and name discovery below.

## Connection and attachment composition

Use an authorized MCP client session already supplied by the host:

```python
scoped = await DiscoveredCanvaSession.discover(client_session, owner_id=principal.owner_id)
capabilities = scoped.capabilities()  # report missing tools before queuing provider work
canva = scoped.adapter(owner_id=principal.owner_id)
```

Or use `async with connect_canva(owner_id=principal.owner_id, access_token=fresh_canva_access_token) as scoped:`. This uses the installed MCP SDK's Streamable HTTP transport at Canva's [documented endpoint](https://www.canva.dev/docs/apps/mcp/verify-app/) `https://mcp.canva.com/mcp`, with a dedicated server-side HTTP client, no redirects and no environment proxies. The already-authorized token comes from Member 2's vault. The factory does not register a client, obtain/refresh tokens, transfer this chat's Canva grant, or install a Go connector. Native HTTP authentication remains a live test once an approved client/token exists. Do not infer a working Go connection from this chat's capabilities.

`RevisionedAttachmentSource(repository, error_factory=WorkflowError)` plugs directly into `Distributor(..., attachments=source)` in Member 3's composition. Default requires one reviewed `flyer_png`; pass `kinds=("flyer_png", "event_document")` to include the reviewed HTML document too. Exact return: `list[tuple[filename, mime_type, bytes]]`. Names are deterministic `event-{id}-r{revision}-flyer.png` / `...-details.html`, never an untrusted event title.

Member 2's `AttachmentRepository` must implement:

```python
async def assert_current(owner_id: str, event_id: str, revision: int) -> None: ...
async def current_asset(owner_id: str, event_id: str, kind: AssetKind) -> AssetRecord | None: ...
async def read_bytes(owner_id: str, object_key: str, *, max_bytes: int) -> bytes: ...
```

**Member 2's Storage implementation is now available on its integration branch.** No new repository method is needed to try this interface: our `SupabaseAttachmentRepository(storage, download_client, storage_origin=settings.supabase_url)` bridges its public `SupabaseAssetStorage.assert_current`, `repo.event_children`, and `signed_url` methods to the read port. Use a dedicated unauthenticated `httpx.AsyncClient` for `download_client`, then pass the bridge to `RevisionedAttachmentSource`. The bridge validates origin/object path, rejects redirects and bearer/API-key/cookie-bearing clients, bounds streamed bytes and never persists the signed URL. HTTPS is required except explicitly configured loopback HTTP for local Supabase. Its listing uses the existing bounded child-record API and fails closed if no current asset is found; long histories should use a paginated/current-only metadata query supplied by Member 2.

```python
# Member 2/3 composition after merging this branch; credentials remain server-side.
storage = SupabaseAssetStorage(database, principal.owner_id)
reader = SupabaseAttachmentRepository(storage, download_client,
                                     storage_origin=settings.supabase_url)
attachments = RevisionedAttachmentSource(reader, error_factory=WorkflowError)
# Inject attachments into Distributor(...); preflight before Calendar writes.
```

Member 2 already has its own `SupabaseAttachmentSource` in the current composition. Adopt this guarded adapter/bridge in that composition or incorporate its required-artifact/aggregate-limit/revision-recheck behavior there; do not run two attachment writers. Our bridge requires no schema or peer-owned file changes. A mocked-HTTP test exercises Member 2's actual Storage write/publish/sign methods through the bridge and verifies the returned PNG bytes.

Authorization and bounded reads happen inside the repository. The adapter independently checks owner/event/revision, review state, canonical object path, MIME, Canva export/design/Go generation provenance, length and SHA-256; validates PNG headers/document UTF-8; checks the event revision again after loading. Missing/unreviewed artifacts raise `needs_review`; stale revisions raise `revision_conflict`; wrong owner raises `forbidden`; integrity/Storage errors raise sanitized `provider_failed`. Default budgets are 10 MB per file and 15 MB total raw bytes. It never fetches arbitrary URLs or falls back to an old export. `error_factory=WorkflowError` maps these directly to Member 3's error type without importing that unmerged branch.

**Member 3 integration requirement:** preflight `current_attachments` before any Calendar invitation side effect, not only inside Gmail MIME construction. The existing upstream distributor loads attachments after Calendar upsert, so composition must add this preflight/review gate to avoid learning about missing flyers only after a Calendar invite. Recheck current event/review state before the send step as well. These peer-owned workflow edits are not made by Member 4.

Compatibility was tested against Member 3 commit `40304bb` and then Member 2's integrated backend `4ec2367` in disposable source overlays: actual `Distributor._mime` embeds exact PNG bytes/revision, the Go asset queue/content loader matches our inputs, and actual Supabase Storage write/publish/sign methods feed our read bridge via mocked HTTP. No peer files are merged or edited; no live Storage account round trip is claimed. The script defaults to Member 2's integration branch (which includes Member 3); pass an explicit Git ref to test another snapshot. Reproduce:

```sh
uv run --project backend --frozen --extra dev python docs/canva/check_member3_compat.py
```

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

`EditPreview` and `FlyerReviewPreview` are server state; use their `preview_metadata()` methods plus a server-owned operation ID for the UI. Keep transaction handles server-side. Show the actual preview, a review button tied to operation/digest/revision, and separate `Update`/`Publish` actions. A newer event invalidates this review. Never let the browser construct `VerifiedDesign`, `Approval`, or provenance records as trusted facts. Signed preview URLs expire: refresh the preview and obtain a new approval instead of silently substituting a different thumbnail.

Use [generated JSON schemas](member4.schemas.json) for adapter types while Member 2 freezes the canonical API. These are Member 4 proposals and do not replace `INTEGRATION_CONTRACT.md`. All inclusion findings are organizer-private; see [inclusion contract](../inclusion/CONTRACT.md).
