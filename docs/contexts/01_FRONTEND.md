# Member 1 context: frontend

Owner: Member 1 (human name/GitHub pending). Updated 2026-10-16. Status: **assigned; product implementation not started by this handoff**.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), [all four member contexts](../TEAM_TASKS.md), and [contract](../INTEGRATION_CONTRACT.md) before work. Write only this personal context; other agents read it but do not edit it. [Copy-ready prompt](../prompts/01_FRONTEND.md).

## Scope

Own `frontend/**`: React/TSX organizer website, Supabase Auth client UI, three-step creation flow, event dashboard, review/update UI, and private RSVP display. Public event page shows approved facts/assets only. Do not edit backend, migrations, or another member's context.

## First deliverables

1. Agree login/token flow and event/review/operation/RSVP schemas with Member 2 using a typed API adapter.
2. Build details → design/inclusion → distribution. Make **Superhuman Go** generation/coordination visible, with truthful waiting/review/failed/live states and editable generated text.
3. Show Canva preview/edit link, current event document, inclusion questions/unknowns, invitation preview, and explicit publish/update review.
4. Show the changed fields and per-artifact event revision; show draft updated vs a new notification after send; do not imply old attachments mutate.

## Dependencies and handoffs

- Need from 2: exact schemas, Supabase client public configuration, verified auth/session behavior, private/public endpoint rules, storage-link access.
- Need from 3: Go work/receipt states, Calendar/Gmail links and status, RSVP schema, actionable account setup errors.
- Need from 4: inclusion finding schema, flyer/export/document metadata, plain-language/accessible content states.
- Supply to 2/3/4: API changes needed, route/component behavior, screenshots, exact reproduction steps, and accessible UI test outcomes.

## Decisions and progress

- Agreed from user: React/TSX; organizer login; three creation stages; updates and RSVP view. Name remains undecided.
- Proposed: exact UI/REST shapes await the first contract handoff. Mock fixtures may unblock UI but must remain clearly labeled and separate from live evidence.
- Verification: existing starter UI passed historical tests; new event screens have not been built/tested.
- Blockers: account/API schemas and live integration outputs pending.
- Next action: start [assigned prompt](../prompts/01_FRONTEND.md), read the other contexts, and publish the first typed UI/API handoff here.

## Update format

`Date | branch/commit/PR | proposed/agreed/implemented/tested/blocked | change and source | contract impact | checks/evidence | blocker | next owner/action`. Keep only material, current handoffs; link superseded decisions and never include credentials or personal attendee data.
