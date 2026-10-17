# Two-minute event-update demo

Member 4 working script, 2026-10-16. Website name undecided. Primary track recommendation: Productivity, with inclusion review demonstrated as a core feature. Final track belongs to the team lead. Rubric mapping follows the team's [hackathon brief](HACKATHON.md); no weights or guaranteed scores are assumed.

**Current readiness:** Member 3 reports a live Go writing/publish loop and a revision-2 time/location update with the same Calendar ID, a new change-notice email in the same thread, duplicate-free retry, and RSVP sync returning `no_response` (`1752141`). These are owner-reported dev-mode results, not hosted Supabase proof. Member 3's asset coordinator is now registered (`d5ce546`, in main `973bdb9`). Member 4's new acceptance tests verify the actual registered app → five synthetic Go-kind saves → document → Canva adapter/read-back/organizer approval → export/Storage → Gmail PNG MIME path using account/HTTP doubles, including history and preflight. Full backend: 304 passed, one optional ML skip. A standalone fictional Canva flyer was created live earlier through this chat; no website Canva OAuth, five actual Go asset outputs, live export/Storage delivery or complete cross-provider run is verified. See [asset wiring handoff](canva/ASSET_WIRING_HANDOFF.md). This script remains a live rehearsal plan.

## Story and speaking cues

Use a fictional, clearly labeled campus workshop with consent-based test recipients. Start with a prepared, reviewed revision 1 so two minutes is enough. Show the actual Go run/receipt from preparation; label any recorded backup with its recording time.

| Time | Presenter cue | Operator action and required evidence |
| --- | --- | --- |
| 0:00–0:15 | “You organize a campus workshop. The room changes an hour before it starts. Now the calendar, email, flyer and event document all need to agree. One missed update sends someone to the wrong place.” | Show the real revision-1 event and current artifact statuses. |
| 0:15–0:32 | “We enter the event once. Superhuman Go writes the invitation, plain-language summary, document and custom flyer brief. Canva turns that brief into an editable design. The organizer reviews the result before anything is sent.” | Show a real Go generation reference and its prose, the custom Canva design, and review screen. Show Go's built-in Grammarly assistance on the actual writing surface. |
| 0:32–0:48 | “Before distribution, we check the entrance, elevator, food, religious holidays from Google's public holiday calendars, captions, loud sound and strobes. If something is unknown, we keep it unknown so the organizer can check it.” | Show one sourced fact and one unknown. Keep private attendee needs off screen. Do not call a sourced answer an accessibility certification. |
| 0:48–1:12 | “Now I change the time and room. Go prepares the revised wording. We can see exactly what will change and approve this revision.” | Save revision 2, show awaiting-Go/running status, actual returned output, new Canva version preview and explicit organizer approval. The current coordinator creates a new design per revision; same-design editing is not registered. If this takes longer than rehearsed, use a disclosed continuous recording of this same run. Never substitute synthetic success into the live UI. |
| 1:12–1:42 | “The calendar keeps its event ID. Canva has the updated details, and we store a new flyer export and document. If the invitation was already sent, we prepare a new change notice. The old email and attachment remain part of the history; the current link points to the latest version.” | Open Calendar and confirm new time/location and same ID. Show Canva saved text and actual new export. Compare document revision/hash, then show the new Gmail draft for a previously sent invitation. Send only if the test publish/update action authorizes it. Show provider receipts, not just green badges. |
| 1:42–2:00 | “Superhuman Go handles the writing and coordination. Our revision checks keep the tools working from the same event. [State the one remaining manual step, if any.] The organizer can make a change and see which materials are current and which still need attention.” | Show the revision/status overview. If RSVP is ready, show a test Calendar response without extending the pitch. Finish on the actual working state. |

The spoken wording is a team pitch draft, not generated event prose. All actual event descriptions, invitations, summaries, documents and flyer copy must come through Member 3's Superhuman Go workflow.

## Demo acceptance checklist

- [ ] Consent-based test organizer/recipient accounts; no real audience list or private needs.
- [ ] Go reads the authenticated event and stores all five asset kinds (`flyer_brief`, `flyer_copy`, `event_document`, `plain_language_summary`, `flyer_alt_text`) with current revision and generation IDs; no hidden substitute model. Use the [rehearsal prompt](canva/GO_ASSET_REHEARSAL.md).
- [ ] Asset preparation shows actual missing/unreviewed kinds; the document is not stored until both its Go prose and summary exist. A stored review draft is not a reviewed/published artifact.
- [ ] Custom Canva creation completes through MCP without a template; organizer edits the actual design.
- [ ] UI renders the real inclusion report with sources and unknowns.
- [ ] Revised time AND location appear in a saved, reviewed Canva design; old values checked and layout inspected.
- [ ] Actual exported PNG stored with export ID/hash/revision; stable current URL resolves the new version and old bytes remain unchanged.
- [ ] Go document changes and its new stored HTML is visually inspected; old version remains retrievable by authorized organizer.
- [ ] Same Calendar event ID reads back revised details, with attendee notifications intentional.
- [ ] Unsent draft replacement and previously-sent → new change-draft behavior verified separately. This pitch uses the latter. A missing draft is not proof it was sent.
- [ ] New event revision during preparation visibly supersedes stale jobs; retry does not duplicate external writes.
- [ ] Two-minute rehearsal with actual latency, disclosure of manual Go invocation if used, and provider failure visible.

## Rubric evidence to prioritize

| Criterion | Show |
| --- | --- |
| Impact & Usefulness | The wrong-room/wrong-time scenario and fewer separate places for the organizer to edit; no unmeasured time-saved claims. |
| Agent Integration | Real Superhuman Go event read, prose outputs and tool receipts, with Grammarly assistance built into Go. |
| Technical Execution | Actual revision-1 → revision-2 read-backs, immutable artifact hashes, same Calendar binding and explicitly tracked Canva version/export IDs, visible partial failures. |
| Creativity & Innovation | Change propagation and inclusion review in one workflow. Do not claim no other team has built something similar. |
| User Experience | Three creation steps, editable design, readable summary, explicit review and clear unknown/stale states. |

## Preparation and fallback

Presenter explains the problem and Go's role; operator controls the browser; Member 2 checks provider/version receipts; backup presenter tracks the clock. Assign humans when the roster is known.

Arrange tabs before rehearsal: organizer review → Go receipt/supported writing surface → Canva → Calendar → Gmail → artifact history. Keep service credentials and personal account data out of recordings. Four optional slides: problem; Go-centered flow; demo cue with verified screenshot; measured outcome/current limits. No deck or export exists yet; use actual screenshots when available.

If a provider fails, show its actual pending/failed state. A timestamped recording of a prior successful run is an acceptable disclosed backup; local fixtures demonstrate service behavior only. If no prior live run exists, say which step remains unverified. Do not claim the entire change propagated if only local HTML or an API double changed.

This rehearsal document does not initiate invitations, public assets, deployment or a Devpost submission. Preserve the pre-existing scaffold disclosure in submission credits.
