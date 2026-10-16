"""Go-assisted work queue: the website enqueues, a Go session claims and saves Go-written prose.

No backend-to-Go inference API exists. Work stays `awaiting_go` until a real Go session calls the
MCP tools, so the website can show that state truthfully instead of faking completion.
"""

from hackathon_backend.workflows.models import (
    ContentKind,
    EventSnapshot,
    GeneratedContent,
    Producer,
    WorkItem,
    WorkKind,
    utcnow,
)
from hackathon_backend.workflows.ports import RevisionConflict, WorkflowStore

OPEN_STATES = {"awaiting_go", "running"}
PREPARE_KINDS = [ContentKind.DESCRIPTION, ContentKind.SUMMARY, ContentKind.INVITATION]
DEFAULT_BATCH = "event_prose"


class WorkflowError(Exception):
    """Typed error whose `code` matches the contract vocabulary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


async def require_event(store: WorkflowStore, owner_id: str, event_id: str) -> EventSnapshot:
    event = await store.get_event(owner_id, event_id)
    if event is None:
        # Same error for missing and foreign events so IDs cannot be probed.
        raise WorkflowError("forbidden", "event not found for this organizer")
    return event


async def enqueue_preparation(
    store: WorkflowStore,
    owner_id: str,
    event_id: str,
    kinds: list[ContentKind] | None = None,
    *,
    batch: str = DEFAULT_BATCH,
) -> WorkItem:
    """Called by the website after saving a revision. Supersedes older open work of this batch."""
    event = await require_event(store, owner_id, event_id)
    for item in await store.list_work(owner_id, OPEN_STATES):
        if (
            item.event_id == event_id
            and item.kind == WorkKind.PREPARE_CONTENT
            and item.payload.get("batch", DEFAULT_BATCH) == batch
        ):
            await store.put_work(item.model_copy(update={"state": "superseded"}))
    requested = list(kinds or PREPARE_KINDS)
    previously_sent = (await store.get_gmail_binding(owner_id, event_id)) is not None
    if batch == DEFAULT_BATCH and previously_sent and ContentKind.CHANGE_NOTICE not in requested:
        requested.append(ContentKind.CHANGE_NOTICE)
    item = WorkItem(
        owner_id=owner_id,
        event_id=event_id,
        event_revision=event.revision,
        kind=WorkKind.PREPARE_CONTENT,
        payload={"kinds": [k.value for k in requested], "batch": batch},
    )
    await store.put_work(item)
    return item


async def list_open_work(store: WorkflowStore, owner_id: str) -> list[WorkItem]:
    items = await store.list_work(owner_id, OPEN_STATES)
    fresh = []
    for item in items:
        event = await store.get_event(owner_id, item.event_id)
        stale = item.kind == WorkKind.PREPARE_CONTENT and (
            event is None or event.revision != item.event_revision
        )
        if stale:
            await store.put_work(item.model_copy(update={"state": "superseded"}))
        else:
            fresh.append(item)
    return fresh


async def claim_work(store: WorkflowStore, owner_id: str, work_id: str) -> WorkItem:
    item = await store.get_work(owner_id, work_id)
    if item is None:
        raise WorkflowError("forbidden", "work item not found for this organizer")
    if item.state not in OPEN_STATES:
        raise WorkflowError("revision_conflict", f"work item is {item.state}")
    claimed = item.model_copy(update={"state": "running", "claimed_at": utcnow()})
    await store.put_work(claimed)
    return claimed


async def save_go_content(
    store: WorkflowStore,
    owner_id: str,
    *,
    event_id: str,
    expected_revision: int,
    kind: ContentKind,
    body: str,
    subject: str | None = None,
    work_id: str | None = None,
) -> GeneratedContent:
    """Persist prose written by Go. Only callable through the Go MCP tool, so producer is fixed."""
    await require_event(store, owner_id, event_id)
    if kind in (ContentKind.INVITATION, ContentKind.CHANGE_NOTICE) and not subject:
        raise WorkflowError("needs_review", "email content requires a subject")
    content = GeneratedContent(
        event_id=event_id,
        event_revision=expected_revision,
        kind=kind,
        subject=subject,
        body=body,
        producer=Producer.SUPERHUMAN_GO,
    )
    try:
        saved = await store.save_content(owner_id, content, expected_revision)
    except RevisionConflict as conflict:
        raise WorkflowError("revision_conflict", str(conflict)) from None
    if work_id:
        await _complete_if_done(store, owner_id, work_id, event_id, expected_revision)
    return saved


async def _complete_if_done(
    store: WorkflowStore, owner_id: str, work_id: str, event_id: str, revision: int
) -> None:
    item = await store.get_work(owner_id, work_id)
    if item is None or item.event_id != event_id or item.state not in OPEN_STATES:
        return
    for kind in item.payload.get("kinds", []):
        if await store.latest_content(owner_id, event_id, revision, ContentKind(kind)) is None:
            return
    await store.put_work(item.model_copy(update={"state": "succeeded"}))
