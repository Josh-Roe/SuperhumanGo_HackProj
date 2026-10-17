"""The guided Go pipeline: one conversation walks the organizer from details to RSVPs.

User decision 2026-10-16: the organizer approves drafts and sending inside the Superhuman Go
chat. Go's per-call confirmation on these tools is the organizer's action; the backend still
records an exact-content Approval, so `Distributor.execute` keeps every existing guarantee
(current revision, reviewed content, idempotent provider steps).

`ChatApprovals` writes the organizer-side records (draft review, approval, inclusion facts).
Supabase mode calls Member 2's `OrganizerRepository` RPCs with the token-resolved owner; dev
mode and tests use the in-memory store.
"""

from typing import Any, Protocol

from hackathon_backend.config import Settings
from hackathon_backend.domain.models import DomainError
from hackathon_backend.workflows.distribution import Distributor
from hackathon_backend.workflows.go_work import WorkflowError, require_event
from hackathon_backend.workflows.memory import InMemoryWorkflowStore
from hackathon_backend.workflows.models import Approval, ContentKind, Producer, new_id, utcnow
from hackathon_backend.workflows.ports import WorkflowStore


class ChatApprovals(Protocol):
    async def mark_ready(
        self, owner_id: str, content_id: str, revision: int, body: str | None, subject: str | None
    ) -> dict[str, Any]: ...

    async def approve(
        self, owner_id: str, event_id: str, revision: int, content_id: str, action: str
    ) -> str:
        """Record the organizer's approval of this exact content; idempotent. Returns its id."""
        ...

    async def inclusion_facts(self, owner_id: str, event_id: str) -> dict[str, Any] | None:
        """`{"version", "event_revision", "facts"}` or None when nothing is saved yet."""
        ...

    async def save_inclusion(
        self, owner_id: str, event_id: str, expected_version: int, facts: dict[str, Any]
    ) -> dict[str, Any]: ...


async def _domain(coro):
    try:
        return await coro
    except DomainError as error:
        raise WorkflowError(error.code, error.message) from None


class SupabaseChatApprovals:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _repo(self, owner_id: str):
        from hackathon_backend.api.dependencies import task_repository
        from hackathon_backend.workflows.models import Principal

        return task_repository(self.settings, Principal(owner_id=owner_id))

    async def mark_ready(self, owner_id, content_id, revision, body, subject):
        repo = self._repo(owner_id)
        return await _domain(repo.review_content(content_id, revision, body, subject))

    async def approve(self, owner_id, event_id, revision, content_id, action):
        repo = self._repo(owner_id)
        row = await _domain(repo.approve(event_id, revision, content_id, action, True))
        return str(row["id"])

    async def inclusion_facts(self, owner_id, event_id):
        return await _domain(self._repo(owner_id).inclusion_facts(event_id))

    async def save_inclusion(self, owner_id, event_id, expected_version, facts):
        repo = self._repo(owner_id)
        return await _domain(repo.save_inclusion_facts(event_id, expected_version, facts))


class MemoryChatApprovals:
    """Dev mode and tests: the same rules as the Supabase RPCs, over the in-memory store."""

    def __init__(self, store: InMemoryWorkflowStore) -> None:
        self.store = store
        self.inclusion: dict[str, dict[str, Any]] = {}

    async def _current(self, owner_id, event_id, revision):
        event = await require_event(self.store, owner_id, event_id)
        if event.revision != revision:
            raise WorkflowError("revision_conflict", f"event is at revision {event.revision}")
        return event

    async def mark_ready(self, owner_id, content_id, revision, body, subject):
        content = await self.store.get_content(owner_id, content_id)
        if content is None:
            raise WorkflowError("forbidden", "content not found for this organizer")
        await self._current(owner_id, content.event_id, revision)
        if content.event_revision != revision:
            raise WorkflowError("revision_conflict", "draft is for an older revision")
        update: dict[str, Any] = {"state": "ready"}
        if body is not None or subject is not None:
            update.update(
                id=new_id(),
                body=body or content.body,
                subject=subject or content.subject,
                producer=Producer.ORGANIZER,
                created_at=utcnow(),
            )
        ready = content.model_copy(update=update)
        self.store.content[ready.id] = ready
        return ready.model_dump(mode="json")

    async def approve(self, owner_id, event_id, revision, content_id, action):
        await self._current(owner_id, event_id, revision)
        content = await self.store.get_content(owner_id, content_id)
        if content is None or content.state != "ready" or content.event_revision != revision:
            raise WorkflowError("needs_review", "approve the draft before sending")
        for approval in self.store.approvals.values():
            same = (approval.event_id, approval.event_revision, approval.action)
            if (
                same == (event_id, revision, action)
                and approval.invitation_content_id == content_id
            ):
                return approval.id
        approval = Approval(
            id=new_id(),
            event_id=event_id,
            event_revision=revision,
            action=action,
            invitation_content_id=content_id,
        )
        self.store.put_approval(approval)
        return approval.id

    async def inclusion_facts(self, owner_id, event_id):
        await require_event(self.store, owner_id, event_id)
        return self.inclusion.get(event_id)

    async def save_inclusion(self, owner_id, event_id, expected_version, facts):
        event = await require_event(self.store, owner_id, event_id)
        version = (self.inclusion.get(event_id) or {}).get("version", 0)
        if version != expected_version:
            raise WorkflowError("revision_conflict", "inclusion facts changed; re-read them")
        row = {"version": version + 1, "event_revision": event.revision, "facts": facts}
        self.inclusion[event_id] = row
        return row


def _stage(name: str, status: str, detail: str) -> dict[str, str]:
    return {"stage": name, "status": status, "detail": detail}


async def event_progress(
    store: WorkflowStore,
    approvals: ChatApprovals,
    distributor: Distributor | None,
    owner_id: str,
    event_id: str,
) -> dict[str, Any]:
    """Where this event is in the pipeline, and the single next step Go should take.

    Status per stage: `done`, `todo`, `optional`, or `blocked`. Read-only.
    """
    event = await require_event(store, owner_id, event_id)
    rev = event.revision
    mail = await store.get_gmail_binding(owner_id, event_id)
    update = bool(mail and mail.sent)
    send_kind = ContentKind.CHANGE_NOTICE if update else ContentKind.INVITATION
    stages = []

    missing = [name for name, value in (("location", event.location),) if not value.strip()]
    if not event.invitees:
        missing.append("guests")
    stages.append(
        _stage(
            "details",
            "todo" if missing else "done",
            f"missing: {', '.join(missing)}" if missing else f"revision {rev} saved",
        )
    )

    kinds = (ContentKind.DESCRIPTION, ContentKind.SUMMARY, send_kind)
    drafts = {kind: await store.latest_content(owner_id, event_id, rev, kind) for kind in kinds}
    unwritten = [kind.value for kind, content in drafts.items() if content is None]
    stages.append(
        _stage(
            "writing",
            "todo" if unwritten else "done",
            f"write for revision {rev}: {', '.join(unwritten)}" if unwritten else "drafts saved",
        )
    )

    send_draft = drafts[send_kind]
    if send_draft is None:
        stages.append(_stage("review", "todo", f"no {send_kind.value} to review yet"))
    elif send_draft.state != "ready":
        stages.append(
            _stage("review", "todo", f"show the {send_kind.value} ({send_draft.id}) for approval")
        )
    else:
        stages.append(_stage("review", "done", f"{send_kind.value} {send_draft.id} approved"))

    facts = await approvals.inclusion_facts(owner_id, event_id)
    if facts is None:
        stages.append(_stage("inclusion", "todo", "ask the access, food and sensory questions"))
    elif facts.get("event_revision", rev) < rev:
        detail = f"saved at revision {facts['event_revision']}; confirm they still hold"
        stages.append(_stage("inclusion", "todo", detail))
    else:
        stages.append(_stage("inclusion", "done", f"facts version {facts['version']} saved"))

    blockers: list[str] = []
    if distributor is None:
        blockers.append("integration_not_connected: Google is not configured on the server")
    else:
        blockers = (await distributor.preview(owner_id, event_id)).blockers
    flyer_required = any("flyer" in blocker for blocker in blockers)
    stages.append(
        _stage(
            "flyer",
            "todo" if flyer_required else "optional",
            "a flyer was started; export it before sending"
            if flyer_required
            else "optional: start_canva_flyer if the organizer wants one",
        )
    )

    sent = bool(mail and mail.sent and mail.event_revision == rev)
    action = "update" if await store.get_calendar_binding(owner_id, event_id) else "publish"
    if sent:
        stages.append(_stage("send", "done", f"revision {rev} sent"))
    elif blockers:
        stages.append(_stage("send", "blocked", "; ".join(blockers)))
    else:
        stages.append(_stage("send", "todo", f"ready to {action}: confirm, then send_invitations"))

    if mail is None or not mail.sent:
        stages.append(_stage("rsvps", "optional", "available after invitations are sent"))
    else:
        latest: dict[str, str] = {}
        for observation in sorted(
            await store.list_rsvps(owner_id, event_id), key=lambda o: o.observed_at
        ):
            latest[observation.invitee_id] = observation.status.value
        counts: dict[str, int] = {}
        for status in latest.values():
            counts[status] = counts.get(status, 0) + 1
        summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "none yet"
        stages.append(_stage("rsvps", "optional", f"{summary}; sync_rsvps to refresh"))

    upcoming = next((s for s in stages if s["status"] in {"todo", "blocked"}), None)
    return {
        "event_id": event_id,
        "revision": rev,
        "title": event.title,
        "mode": "update" if update else "first_send",
        "stages": stages,
        "next_stage": upcoming["stage"] if upcoming else "rsvps",
    }


async def send_invitations(
    store: WorkflowStore,
    approvals: ChatApprovals,
    distributor: Distributor,
    owner_id: str,
    event_id: str,
    expected_revision: int,
) -> dict[str, Any]:
    """Approve the reviewed invitation/change notice for this revision and send it."""
    event = await require_event(store, owner_id, event_id)
    if event.revision != expected_revision:
        raise WorkflowError("revision_conflict", f"event is at revision {event.revision}")
    mail = await store.get_gmail_binding(owner_id, event_id)
    if mail and mail.sent and mail.event_revision == event.revision:
        # Retry of a completed send: replay the same approval so every step returns its receipt.
        sent = await store.get_content(owner_id, mail.content_id)
        action = "publish" if sent and sent.kind == ContentKind.INVITATION else "update"
        approval_id = await approvals.approve(
            owner_id, event_id, event.revision, mail.content_id, action
        )
        result = await distributor.execute(owner_id, event_id, approval_id)
        return {"approval_id": approval_id, "action": action, **result.model_dump(mode="json")}
    plan = await distributor.preview(owner_id, event_id)
    if plan.blockers:
        raise WorkflowError("needs_review", "; ".join(plan.blockers))
    content = await store.latest_content(
        owner_id, event_id, event.revision, plan.required_content_kind
    )
    if content is None:  # preview already blocks this; keeps the type checker honest
        raise WorkflowError("awaiting_go", f"no {plan.required_content_kind.value} saved")
    action = "update" if plan.calendar_action == "update" else "publish"
    approval_id = await approvals.approve(owner_id, event_id, event.revision, content.id, action)
    result = await distributor.execute(owner_id, event_id, approval_id)
    return {"approval_id": approval_id, "action": action, **result.model_dump(mode="json")}
