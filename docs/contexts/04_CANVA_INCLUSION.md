# Member 4 context: Canva, inclusion, documents, presentation

Owner: Member 4 (human name/GitHub pending). Updated 2026-10-16.
Status: **implemented and locally tested; live provider round trip pending**.
Branch: `codex/member-4-canva-inclusion`, based on shared `3bd33b3`.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), all four contexts, [contract](../INTEGRATION_CONTRACT.md), and [assigned prompt](../prompts/04_CANVA_INCLUSION.md) before work. Write only this personal context. Preserve other members' files.

## Accepted decisions

- **2026-10-16, user clarification, agreed:** there is no flyer template. Each event gets a custom Canva document created through MCP. This supersedes template/autofill-first assumptions in the original handoff; no template URL is required.
- Superhuman Go supplies the design brief, displayed flyer copy, event document, summary and alt text. Canva supplies the editable layout. Any additional generated event wording goes back through Go before review; no silent Gemini substitution.
- Inclusion preserves unknowns and dated sources. No personal religion/diagnosis inference or accessibility certification. Reports and attendee needs stay organizer-private.
- Canva editing is staged, then explicitly approved from the actual preview before commit. Revised exports/documents are immutable snapshots; stable current links require Member 2's resolver.

## Implemented interfaces

All Python paths below are relative to `backend/src/hackathon_backend/`.

| Path | Delivery |
| --- | --- |
| `providers/canva/__init__.py` | `CanvaMCPAdapter`: custom creation, asynchronous polling policy/latest token, editor links, live-element mapping validation, staged replacements, exact preview-digest approval, same-design commit, text read-back/stale-value review, completed single-page PNG export handoff. Injectable organizer-scoped MCP executor. |
| `services/assets/models.py` | Strict event/content/design/approval/artifact types; owner and event-revision checks; exact timezone-rendered canonical fields; safe preview metadata. |
| `services/assets/requests.py` | `request_event_prose` → Member 3's durable queue protocol. Five Go content kinds; deterministic owner/event/revision batch key; queue receipt remains queued/awaiting-Go. |
| `services/assets/documents.py` | Escaped semantic HTML using only Go prose plus canonical event fields; language, summary and generation/revision references. No inferred prose or replacement model. |
| `services/assets/storage.py` | Immutable content-hash paths, strict receipts, current-revision CAS, reviewed/unreviewed states, Canva export/design/Go generation metadata. Bounded unauthenticated official-CDN PNG downloader. |
| `services/inclusion/__init__.py` | Plain-language review, step-free entrance, floor/elevator, private diet matching with confirmation, supplied religious-observance interval overlap, captions, loud sound and strobes. Empty observance coverage remains unknown. |

Concrete registration/Storage/UI handoff: [Member 4 integration guide](../canva/MEMBER4_INTEGRATION.md).
Types: [JSON schemas](../canva/member4.schemas.json).
Findings/privacy behavior: [inclusion contract](../inclusion/CONTRACT.md).
Two-minute speaking/demo cues and actual-artifact acceptance gates: [presentation](../PRESENTATION.md).

## Live versus local evidence

- **Live read-only, 2026-10-16:** connected Canva design search and rich-text read succeeded. Autofill-ready template search returned no items; one existing flyer had an empty dataset. No private design text/contact details were copied into Git. No live design creation, edit commit or export was performed.
- **Documented:** official custom `create-design` and transaction/read-back tools support this approach. Account AI credits/admin grants remain untested. Remote MCP documents `export-design`; that tool is absent from this chat's exposed connector. Check the actual host before promising automated export. See linked official sources in the guide.
- **Local/synthetic:** backend suite passes **73 tests, 1 optional test skipped** with base/dev dependencies. Ruff passes. New tests cover changed time/location, exact approval, stale old text, owner/revision rejection, Go-only kinds, queue receipts, sourced/unknown inclusion, observance timezone overlap, private diet findings, HTML escaping, immutable versions, upload races, bad Storage receipts and safe CDN download rules. Fixtures explicitly disclose no live Go or Canva write.
- No Supabase/Auth/RLS, public current link, browser UI, live Go generation, Google synchronization, visual flyer audit or complete two-minute live demo is verified by these tests. Text verification is not layout verification. Document HTML is tested structurally; visual inspection of a real Go document remains a demo gate.

Reproduce from the repository root:

```sh
uv sync --project backend --frozen --extra dev
uv run --project backend --frozen --extra dev pytest backend/tests -q
uv run --project backend --frozen --extra dev ruff check backend
```

The current environment emits one existing Starlette/httpx deprecation warning. Shared dependency files remain Member 2's responsibility.

## Handoffs requiring recipient agreement

**Member 1 — proposed:** consume `AssetRecord.preview_metadata()`, authorized preview/current links, trusted Go alt text, and private `InclusionReport`. Show revision, source dates, unknown/review states and actual transaction thumbnails. Bind the organizer approval action to operation ID/digest/revision. Do not send raw transaction tokens or treat client-constructed provenance as trusted. No frontend files changed.

**Member 2 — proposed:** implement `AssetStorage.assert_current`, `put_if_absent`, atomic owner/revision `publish_current`; private bucket paths and exact metadata in the guide. Add authenticated stable current-link resolution, artifact history, trusted content provenance/review records, encrypted generation continuation tokens, and durable provider operation claims/locks/approvals. Supabase adapter/schema/RLS/auth not implemented by Member 4. Incorporate agreed custom-MCP decision and extra Go content kinds into canonical docs/contracts; those files were not edited here.

**Member 3 — proposed:** implement `GoPreparationQueue.enqueue` and trusted content loading for `flyer_brief`, `flyer_copy`, `event_document`, `plain_language_summary`, `flyer_alt_text`. Supply an organizer-scoped Canva tool session/name map, check grants/tool inventory, persist/reconcile provider jobs, enforce write locks/current revisions, cancel abandoned edit transactions, register adapters through owned composition. Enforce actual preview approval before commit. Record visual review of new and manually edited designs. A provenance string alone does not prove a Go run. No `main.py`, workflow, Google or Go-owner files changed.

## Remaining live gates / next action

1. Member 3 proves Go reads an authorized concrete event and saves the five real asset-prose outputs. Missing website triggers remain visibly awaiting-Go/manual invocation.
2. With that content and the organizer's session, custom-create one flyer; inspect/edit and record the real binding. Verify export permission or explicitly label a manual export/import fallback; never report a manual path as automated MCP export.
3. Member 2 connects scoped Storage and current-link resolver; Member 1 connects review UI. Test revised time/location across real Canva text/PNG, document, Calendar and Gmail receipts using the presentation gates.
4. Only after that run mark the cross-provider demo live. No external sends, deployment, public asset publication or Devpost submission were performed by this task.
