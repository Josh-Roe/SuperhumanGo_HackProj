# Four-member execution plan

Approved direction: event organizer website; name undecided. Superhuman Go supplies the writing/coordination layer and calls our event tools. The source brief is [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md); current interfaces are [here](INTEGRATION_CONTRACT.md).

Send **one** prompt to each member's agent. Each prompt includes the read-all/write-own context rule. These are roles, not assignments to named people yet. Preparing this plan does not start four agents or perform external account actions.

| Member | Assignment | Copy-ready prompt | Only personal context they edit |
| --- | --- | --- | --- |
| 1 | React/TSX organizer and recipient UI | [Frontend](prompts/01_FRONTEND.md) | [Frontend context](contexts/01_FRONTEND.md) |
| 2 | Python, Supabase Auth/data/Storage, contracts, VPS/integration lead | [Backend/Supabase](prompts/02_BACKEND_SUPABASE.md) | [Backend context](contexts/02_BACKEND_SUPABASE.md) |
| 3 | **Superhuman Go**, Gmail, Calendar, change orchestration, RSVP | [Go/Google](prompts/03_GO_GOOGLE.md) | [Go context](contexts/03_GO_GOOGLE.md) |
| 4 | Canva, inclusion, Go-written event documents, presentation | [Canva/inclusion](prompts/04_CANVA_INCLUSION.md) | [Canva/inclusion context](contexts/04_CANVA_INCLUSION.md) |

## Start together, then divide

1. Everyone reads root context plus all four member contexts. Confirm the human behind each role and use separate feature branches/checkouts.
2. Member 2 publishes exact v0 schemas/auth/repository interfaces; Members 1/3/4 confirm their dependencies in their own contexts. Member 3 owns `main.py` registration, while 2 owns dependencies/config/migrations.
3. Member 3 proves **live Go → authorized event read → Go-written content saved**. Member 4 verifies Canva template/edit/export access. Member 2 validates Supabase ownership. Member 1 can build clearly labeled fixtures through an adapter while those handoffs settle.
4. Build one vertical slice: organizer details → Go prose → inclusion/Canva → approved publish → provider receipts. Then add the revision/update path and RSVP.
5. Pair 1+2 for API/auth and 3+4 for Go/Canva/inclusion integration. Reread all contexts before integration; PRs carry context updates. Do not have multiple agents edit one person's context or shared `main.py`/lockfiles.

## Feature sequencing

**Core:** login, event details/timezone/invitees, Go-generated editable prose, Canva flyer and event document, inclusion review, Gmail draft/Calendar invite distribution, versioned updates across artifacts, visible receipts/errors, RSVP tracking.

**After the core works:** Google Forms for extra/private RSVP data, parking/restroom expansion, additional personalization. Plain-language, ramp/elevator, dietary, religious-observance and sensory questions remain in the core inclusion review, even when the truthful result is unknown or organizer input is needed.

**Defer:** custom training, ONNX/C++ optimization, broad unrelated event-platform features. Keep the existing optional scaffolds available without spending the demo window on them.

## Shared definition of done

- A logged-in organizer creates an event with explicit timezone; another account cannot access its private event/RSVP state.
- A real Go session generates and stores event prose through our supported integration; the demo distinguishes Go generation from Python execution.
- Canva flyer/document and invitation represent the reviewed canonical event revision; inclusion answers/unknowns are visible before publishing.
- Approved publishing creates one intended Calendar event and sends the intended Gmail invitation with actual links/current material. Test only with authorized demo recipients.
- Changing time/location updates that Calendar ID, updates or versions the Canva flyer and document, updates an unsent draft or creates a new notification after send, and records read-back evidence. Retries do not duplicate sends.
- At least one Calendar/email RSVP is correctly matched and shown; ambiguous replies go to review. Sensitive needs never leak in public material.
- UI is usable by keyboard/screen reader with text alternatives, responsive layout, and comprehensible pending/error states. No claim of universal accessibility replaces testing.
- Each member's context identifies checks, missing credentials, and next-owner handoffs. Member 2 integrates and verifies CI; Member 4 captures the actual two-minute demo and disclosure.

The local scaffold can be checked with `npm run check`. New unit/integration tests, actual Supabase/provider checks, and browser checks must be recorded separately; SDK compilation alone cannot prove the product works.
