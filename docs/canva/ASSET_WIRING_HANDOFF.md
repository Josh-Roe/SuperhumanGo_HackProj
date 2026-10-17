# Registered asset workflow handoff

Member 4, 2026-10-16. Verified against main `973bdb9`, including Member 3 composition `d5ce546`. This is the single existing coordinator in `workflows/asset_wiring.py`; do not register a second set of asset tools or provider writers. Member 4 did not edit `main.py` or other members' modules.

## What is wired

In Supabase server mode, `main.create_app` registers Member 2's organizer API and Member 3's organizer/asset tools. `register_asset_services` composes:

- The same owner-scoped Go workflow store used by event tools.
- `EventAssetPreparationService` and its five-kind `StoredGoAssetQueue`.
- Owner-bound `SupabaseAssetStorage` for immutable document/flyer writes and current pointers.
- `VaultCanvaSessions` → Member 4's discovered Canva MCP session and adapter.
- Encrypted per-event flyer state and continuation tokens when the credential vault is configured.
- `OwnerScopedAttachments` → `SupabaseAttachmentRepository` → `RevisionedAttachmentSource` → Gmail MIME.
- A started-flyer policy that blocks Calendar/Gmail distribution until a reviewed current flyer is deliverable. Never-started or explicitly abandoned flyers are optional in the current coordinator; that policy is not a guarantee that every invitation contains a flyer.

The REST routes precede the catch-all MCP mount. Production registration requires `SUPABASE_URL` and server-only `SUPABASE_SERVICE_ROLE_KEY`; REST sessions also need the public project key. Canva needs an authorized, server-held account token and `CREDENTIAL_ENCRYPTION_KEY`. Configuration is not evidence that account access works. No Canva OAuth connect/refresh UI exists yet; connecting Canva in this chat does not provision the website's vault.

## Actual Go tools

| Tool | Inputs | Result / authority |
| --- | --- | --- |
| `get_event_assets` | `event_id` | Prose readiness, flyer stage, account/configuration state. |
| `request_asset_prose` | `event_id`, `expected_revision` | Idempotent five-kind queue receipt. It does not wake Go automatically. |
| `prepare_event_document` | Same revision inputs | `awaiting_go` or stored document metadata; preserves review state. |
| `start_canva_flyer` | Same | Creates one custom flyer per revision, or returns the recorded attempt. Requires saved Go brief and displayed copy. |
| `poll_canva_flyer` | Same | Polls a recorded creation after its due time. |
| `preview_canva_flyer` | Same | Read-back and actual thumbnail/digest for organizer review. |
| `export_canva_flyer` | Same | Requires organizer-approved preview, exports and stores the PNG; inspect its stage. |

Each resolves a personal organizer connector token. The deployment token cannot read private event assets. Go saves prose using `save_generated_content`, with the producer fixed by the server. Required asset kinds are `flyer_brief`, `flyer_copy`, `event_document`, `plain_language_summary`, and `flyer_alt_text`. Invitation/change-notice prose remains a separate Go request. No replacement LLM was added.

## Actual organizer routes

All use the organizer's Supabase session bearer token. Prefix: `/api/events/{event_id}/assets`.

| Method / suffix | Body |
| --- | --- |
| `GET` (no suffix) | None; current status. |
| `POST /prose` | `{expected_revision}` |
| `POST /document` | `{expected_revision}` |
| `POST /inclusion` | `{expected_revision, facts: InclusionInput}` |
| `POST /flyer` | `{expected_revision}` |
| `POST /flyer/poll` | `{expected_revision}` |
| `POST /flyer/preview` | `{expected_revision}` |
| `POST /flyer/approve` | `{expected_revision, preview_digest}` copied from the exact server preview. |
| `POST /flyer/export` | `{expected_revision}` |
| `POST /flyer/abandon` | `{expected_revision}`; explicit organizer opt-out. |

Approval/abandon are organizer-only REST actions, not Go tools. Prose review is separate from visual flyer approval. Inclusion checks are private, return sources/unknowns, and are not persisted as a trusted venue certification. The existing flat inclusion-fact table cannot represent all `InclusionInput` facts; a versioned save contract belongs to Member 2.

## Member 1 preview contract

`AssetRecord.preview_metadata()` now returns the schema `AssetPreviewMetadata` in [member4.schemas.json](member4.schemas.json): event ID/revision, kind, MIME, SHA-256, byte length, review state, creation time, Go generation ID, Canva design/export/generation IDs where applicable. These are source references, not secrets or proof of live execution. No owner ID, Storage object key, continuation/transaction token or provider download URL is included.

Member 2's authorized current-asset endpoint adds the short-lived signed `url`. The coordinator's status contains `prose`, `flyer`, `flyer_required_for_invitations`, `canva`, and `storage`. `flyer.preview` contains `digest`, expected canonical fields and thumbnail URLs. Use these existing paths/keys for the separate flyer preview/approve/abandon UI; do not confuse the generic prose-review button with Canva approval.

## Exact remaining owner handoffs

- **Member 3:** registration is complete in main. Preserve the one coordinator. `OwnerScopedAttachments` currently uses the default flyer-only adapter; if both files should be emailed, pass `kinds=("flyer_png", "event_document")` when constructing `RevisionedAttachmentSource`. Both files must then be current and reviewed; do not silently omit an unavailable document. No workflow file was changed by Member 4.
- **Member 2/3:** supply the actual authorized Canva OAuth grant/refresh flow and encrypted vault record; keep token values out of prompts and Git. Replace the process-local lock with a durable lease before multiple workers. Existing vault-held state persists jobs, but does not provide a cross-process lease; the no-vault fallback is in-memory.
- **Member 3:** pending export handling currently calls `request_png_export` again on a later request. A pending export ID is not a polling capability. Resolve provider reconciliation/recovery before claiming duplicate-free asynchronous exports. Recheck canonical revision before returning cached stored/create results, and before abandonment that lifts the attachment requirement.
- **Member 1:** connect the real flyer preview/approve/abandon and inclusion report routes. Current UI generic content review/current artifact reads do not implement these distinct actions.
- **Live rehearsal:** save all five actual Go outputs, create/review/export with the website's authorized Canva session, upload/sign/read on hosted Storage, and inspect the real layout and attachments. This device has not completed that account run. Current coordinator starts a new design/version per event revision; Member 4's staged same-design edit adapter is available but not registered. Do not present a new design as an in-place edit.

## Verification

`backend/tests/test_assets_registered_flow.py` exercises the actual `main.create_app` and `register_asset_services`, actual encrypted vault and Supabase Storage classes over mocked HTTP, actual Canva adapter against synthetic session responses, and actual Gmail MIME against Google fakes. It verifies five Go saves/queue completion, private HTML/PNG storage, exact preview approval, one creation/export on completed retries, PNG attachment bytes, no duplicate fake send, auth separation, unknown inclusion findings, required-flyer preflight before Calendar, and a revised document retaining old bytes/current pointer history.

The workflow store and account responses are doubles. Organizer content/publish approvals are explicitly simulated. The test advances a synthetic stored creation deadline rather than waiting for a real provider. This is transport/composition evidence, not a hosted Supabase, real Go inference, Canva/Google account or visual-layout result. The entire backend suite passes **304 tests**, with one optional ML skip and the existing Starlette/httpx warning.
