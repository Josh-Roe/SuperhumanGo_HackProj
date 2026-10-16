# Member 4 context: Canva, inclusion, documents, presentation

Owner: Member 4 (human name/GitHub pending). Updated 2026-10-16. Status: **assigned; product assets/checks not started by this handoff**.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), [all four member contexts](../TEAM_TASKS.md), and [contract](../INTEGRATION_CONTRACT.md) before work. Write only this personal context. [Copy-ready prompt](../prompts/04_CANVA_INCLUSION.md).

## Scope

Own Canva provider adapter/account callback factory, inclusion and asset/document services, Canva/inclusion guides, product assets, and presentation/demo brief. Member 1 owns all React screens; provide metadata/types rather than editing frontend. Member 3 registers adapter routes/tools and orchestrates Go; 2 owns Storage/database/vault/config/dependencies.

## First deliverables

1. Verify Canva account/template eligibility and field dataset. Support organizer editing and test flyer creation, field updates, exports, stored revision, and a stable current link. Record if updates require a new design/version.
2. Provide inclusion findings with known/unknown/source fields: step-free entrance/elevator, diet, significant religious-observance conflicts, captions, loud sound/strobes, plus Go-written plain-language summary. Ask which observances matter; do not infer personal religion or accommodations.
3. Render Go-written event prose into versioned documents stored through 2's Storage API; prepare plain text/alt text for the flyer. All new prose is requested through 3's Go workflow, not silently generated elsewhere.
4. Prepare an accurate two-minute pitch and demo script showing Go plus one changed time/location updating actual artifacts. Forms, parking/restrooms and extra Notion connection follow the core flow.

## Dependencies and handoffs

- Need from 2: artifact schema, signed/public-link policy, Storage repository, credential vault and migration changes.
- Need from 3: Go-supplied prose/content schema and orchestration calls; give 3 adapters/registration instructions and verify correct event revision.
- Supply to 1: accessible flyer/document preview metadata, edit/current links, finding severity/unknown/acknowledgment fields, loading/failure states.

## Decisions and progress

- Agreed from user: Canva flyer, event document, inclusion before distribution, broad plain-language/physical/diet/religious/sensory checks.
- Verified documentation: Canva structured autofill requires supported data fields/account access; arbitrary text edits and update-in-place must be tested, not assumed.
- Verification: no product flyer, Canva update/export, inclusion checker, or deck has been created in this preparation.
- Blockers: Canva credentials/eligible plan/template, Go content, Storage methods, organizer-supplied venue/diet facts and dated observance source.
- Next action: verify one Canva template/data-field round trip and agree inclusion/artifact schemas with 1/2/3.

## Update format

`Date | branch/commit/PR | status | decision/source | Canva/inclusion/assets contract | checks/evidence | blocker | next owner/action`. Keep sensitive attendee needs out of Git/public assets; distinguish a manual edit or local fallback from live Canva synchronization.
