# Member 4 context: Canva, inclusion, documents, presentation

Owner: Member 4 (human name/GitHub pending). Updated 2026-10-16.
Status: **implemented and locally tested; live provider round trip pending**.
Branch: `codex/member-4-canva-inclusion`, based on shared `3bd33b3`.
Implementation commit: `cdf08bc`. Draft [PR #1](https://github.com/Josh-Roe/SuperhumanGo_HackProj/pull/1) awaits cross-member integration and live proof.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), all four contexts, [contract](../INTEGRATION_CONTRACT.md), and [assigned prompt](../prompts/04_CANVA_INCLUSION.md) before work. Write only this personal context. Preserve other members' files.

## Accepted decisions

- **2026-10-16, user clarification, agreed:** there is no flyer template. Each event gets a custom Canva document created through MCP. This supersedes template/autofill-first assumptions in the original handoff; no template URL is required.
- Superhuman Go supplies the design brief, displayed flyer copy, event document, summary and alt text. Canva supplies the editable layout. Any additional generated event wording goes back through Go before review; no silent Gemini substitution.
- Inclusion preserves unknowns and dated sources. No personal religion/diagnosis inference or accessibility certification. Reports and attendee needs stay organizer-private.
- Canva editing is staged, then explicitly approved from the actual preview before commit. Revised exports/documents are immutable snapshots; stable current links require Member 2's resolver.

### Go-led website workflow clarification — 2026-10-16

**Agreed product direction, source: team lead's current chat:** the website backend exposes an authenticated hosted MCP server. Go connects to it, creates tasks/events, prepares the custom Canva flyer and email, coordinates Calendar creation/updates, and saves event changes/results back through website tools. The website displays the canonical saved state. Manual website editing remains available, consistent with Member 1's latest handoff.

Go is the orchestrator; the backend still validates owner, expected revision, approvals and provider receipts. “Edit the website” means authorized tools update the same canonical event/task records used by the UI, not arbitrary page/DOM editing. Existing organizer review/publish requirements remain in effect: preparing an email draft is distinct from sending it, and Calendar invitations are a publication side effect.

**Proposed implementation handoff:** Member 3 adds create/update event/task tools backed by Member 2's canonical repositories, returning event/task IDs and revisions. Exact tool names and a separate task schema remain to be agreed; they are not implemented by Member 4. Preserve Member 3's backend OAuth adapters as the single Gmail/Calendar writer; Go invokes those tools rather than also writing through native Google connectors. For Canva, use either the authorized direct Go connector or our backend adapter as the writer for a given operation, and save the resulting design/export IDs and revision through website tools.

**Trigger limitation remains unverified:** connecting Go to MCP exposes tools but does not itself wake Go when the website changes. Once started by an organizer prompt or a supported, tested trigger, Go should carry the preparation sequence through to review. Until account-side automation is proven, show `awaiting_go` rather than promise a website button automatically starts Go. [Hosted MCP/confirmation guidance](https://coda.io/packs/build/latest/guides/blocks/mcp/) and [supported agent triggers](https://support.grammarly.com/hc/en-us/articles/47453002811021-Create-and-configure-agents-with-the-agent-builder) were rechecked on 2026-10-16.

**Latest cross-member read:** upstream `codex/member-1-frontend` already records Go-led creation and manual editing; its pending Canva preview-approval action matches this requirement. Upstream `codex/member-3-go-google` implements the asset queue/Go-content loader locally, but its context does not yet report create/update task/event tools or a live Go/Canva proof. These are read handoffs, not merged or independently verified integration claims. Member 2 should incorporate the agreed workflow into canonical docs; other members' contexts remain untouched.

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

- **Initial live read-only checks, 2026-10-16:** connected Canva design search and rich-text read succeeded. Autofill-ready template search returned no items; one existing flyer had an empty dataset. No private design text/contact details were copied into Git.
- **Subsequent user-authorized live sample, 2026-10-16:** this chat's Canva MCP `create-design` job completed and produced editable design `DAHYNrfTZeA`, [sample flyer](https://canva.link/grhcsa0uscrdawo). Read-back confirmed its supplied event text and fictional-details label. This was a standalone visual sample with placeholder copy, not Go-generated product content. It proves creation through this chat's connected Canva account; no Go execution, edit commit, export or Supabase round trip is proven. The completion returned a `canva.link` shortlink; Member 4 must normalize it using `get-design` metadata before the adapter's existing `canva.com` URL validator can accept this live response shape.
- **Documented:** official custom `create-design` and transaction/read-back tools support this approach. The sample demonstrates available generation access in this chat, not Go's account grants or ongoing credit availability. Remote MCP documents `export-design`; that tool is absent from this chat's exposed connector. Check the actual host before promising automated export. See linked official sources in the guide.
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
4. Only after that run mark the cross-provider demo live. The user-authorized sample Canva design above is the only live creation recorded here; no invitations, deployment or Devpost submission were performed.
