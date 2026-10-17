# Member 2 API handoff v0.3

Implemented factories; Member 3 owns registration. New consumer mapping is proposed
until accepted by Members 1/3. Existing canonical CRUD/read shapes are retained.
Export the exact 24-path, 42-component OpenAPI contract:

```sh
uv run --project backend --frozen python -m hackathon_backend.api.schema
```

Private routes use Supabase `Authorization: Bearer <session>`; request bodies never
choose owner IDs. Errors: `{detail:{code,message}}`, stale revision 409, foreign ID
404, missing/expired identity 401. Responses/errors are not cached. No provider token
or continuation state is returned.

## Records and complete reads

`GET/POST /api/events`, `GET/PUT /api/events/{id}` and matching `/tasks` use existing
strict models. Create requires `Idempotency-Key`; reuse it after a timeout. PUT uses
all editable fields plus `expected_revision`. `/revisions` returns immutable history.

`POST .../prepare` with `{expected_revision}` returns a durable `WorkItem` (202).
Its event/revision key deduplicates invitation and five-kind asset preparation. It
does not trigger Go or generate prose; pending work remains visibly awaiting Go.

`GET .../workspace` → `WorkspaceResponse`: `event`, `generated_content`, `artifacts`
(safe metadata/current flag/saved row ID), `inclusion_facts`, `work`, `operations`,
`rsvps`, `calendar`, `gmail`, `approvals`, `truncated`. Child records keep their own
revisions; a revision race returns 409. Never treat stale history as current.
Lists cap at 500 children; truncation flags mean incomplete history. Worker summaries
omit arbitrary payloads, continuations and reply bodies. RSVP data stays private.

Existing `/review`, `/operations`, `/rsvps`, `/artifacts` remain for Member 1 PR #6.
Narrow reads: `GET .../work`, `GET .../bindings` → `{calendar,gmail}` (nullable),
`GET .../approvals` → `Approval[]`. Recover durable IDs after reload, including unsent
versus sent Gmail bindings. An approval is not a send receipt.

## Review and distribution

`POST /api/content/{content_id}/review` with `{expected_revision,body?,subject?}`
reviews saved content. Editing creates a new organizer-produced content ID. Refresh
and approve that ID; edits never silently retain Go provenance.

`POST .../approvals` retains the existing body:

```json
{"expected_revision":1,"action":"publish","invitation_content_id":"<saved-content-uuid>","acknowledged_unknowns":true}
```

Identical owner/event/revision/action/content requests now return the **same saved
approval**, serialized by the event lock. Retry after timeout/reload is safe. Changed
action/content gets a distinct approval; stale revisions fail. Recover via `/approvals`.

`POST .../distribution/preview` with `{expected_revision}` returns Member 3's plan
and blockers. `POST .../distribution/execute` with `{expected_revision,approval_id}`
invokes the same server coordinator used by Go and returns actual operation receipts
and sent status. It cannot create approvals. Reuse the saved approval ID on retry;
operation keys enforce idempotency. Member 1 may retain its manual Go execution prompt.
Both execution paths require an organizer publish/update action.

Production factory uses `PersistentDistributor`: require **both** reviewed current
flyer PNG and rendered document; validate source IDs/type/path/revision/hash/size;
load and pin immutable bytes **before** any Calendar/Gmail write. MIME construction
uses those exact bytes, isolated across concurrent organizers. Missing, stale,
unreviewed or corrupt files block; no flyerless fallback.

`GET .../artifacts/{flyer_png|event_document}/current` returns a short-lived private
signed URL. `POST .../artifacts/{artifact_id}/review` with `{expected_revision,sha256}`
reviews exact saved export bytes/current pointer, persisting a retry-safe receipt.
Browser grants cannot forge provider metadata. **Stored-export review does not approve
or commit a staged Canva transaction.** Preview/digest/session coordination remains
the Member 3/4 handoff.

## Versioned private inclusion

`GET .../inclusion` → `{event_id,event_revision,facts_saved,facts,report}`. `facts` uses
Member 4's exact `InclusionInput`; `report` is its actual private `InclusionReport`.
Absent confirmations preserve unknown. Local rules are not a venue/holiday lookup.

`PUT .../inclusion` with `{expected_revision,facts: InclusionInput}` atomically saves
source/date/observance/private diet inputs and returns a **new EventRecord revision**.
It invalidates old assets, prose/jobs and approvals. Refresh, prepare through Go and
review again. Retrying the prior revision returns 409; reload and compare saved facts.
Facts cannot silently change under a previous approval.

Trusted export review/inclusion saves require server credentials after the user
session authorizes the event. Legacy flattened fact columns stay unknown because one
source/date cannot represent independent confirmations. Member 1 maps `facts` from
the new endpoint, rather than inferring legacy confirmations. Inputs/reports are
owner-only under RLS and must never be logged, attached or copied into shared invites.
