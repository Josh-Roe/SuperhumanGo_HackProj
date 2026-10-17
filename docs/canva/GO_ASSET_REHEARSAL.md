# First Go asset-prose rehearsal

Member 4, 2026-10-16. Member 3 reports the live Go read/write loop and authorized Google test publish worked; the three saved core kinds do not yet supply all five asset kinds. This prompt completes the next evidence gate using its currently implemented read/claim/save tools. It does not install a connector, start an automatic trigger or publish invitations.

Use the actual authorized test event ID returned by Member 3. Its development fixture is `dev-event-1`; a Supabase event uses its real UUID instead. Do not assume the fixture exists on another host. Paste the prompt in the organizer's already connected Superhuman Go session and provide the event ID. Approve each Go write only after reviewing its proposed tool action.

> Use our Event Workspace connector to read my test event by its exact saved ID. Confirm the current revision, title, time, timezone and location from get_event; ask me for the ID if I have not supplied it. Do not create a second event or invent missing facts.
>
> Prepare five separate outputs: flyer_brief for Canva layout instructions, flyer_copy for the actual displayed flyer text, event_document for event details, plain_language_summary for a clear summary, and flyer_alt_text for an accessible description of the intended flyer. Base factual statements only on the saved event and organizer-confirmed facts. Do not invent confirmed venue access, diets, captions, holidays or sensory accommodations. Keep private guest information out of every output. The alt text must describe the intended content without claiming an uninspected visual design already exists; it will need review against the real design.
>
> Call save_generated_content separately for each output, using its exact kind and current expected_revision. If a matching five-kind asset_prose work item exists, claim it and pass its work_id with each save. Otherwise save the content without a work_id; do not mark an unrelated event-prose job complete. Follow any tool-confirmation request. On revision_conflict, stop and reread the event before drafting again.
>
> Reread get_event afterward and return the saved event ID/revision plus all five output IDs and their review states. If a save failed, report exactly which kind is missing. Do not claim completion from prose shown only in this chat. Leave organizer review pending. Do not send email, create Calendar invitations, approve Canva edits or claim that any provider has synchronized.

After the run, Member 3 uses `EventAssetPreparationService.read` against the **same store/account/event**, then `prepare_document` and the private inclusion review. Member 4's preview DTO lists missing/unreviewed kinds and generation IDs. Actual Canva jobs and export IDs remain separate evidence. A browser using the frontend's local sample store will not display data saved to the development or Supabase store.

For revision 2, change canonical time/location through an available authorized event-edit path, then rerun the five saves for the same ID at the new revision. Old prose must not be reused as current. Follow the [demo acceptance checklist](../PRESENTATION.md) for actual Canva/export/Storage/Google verification.
