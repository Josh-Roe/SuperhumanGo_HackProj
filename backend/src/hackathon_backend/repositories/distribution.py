"""Persistent composition: verify attachments before any Calendar invitation.

Member 3's workflow remains the provider executor. This adapter pins the verified
immutable bytes for one execution, including concurrent organizers, so the MIME
builder uses exactly the files that passed preflight.
"""

from contextvars import ContextVar

from hackathon_backend.workflows.distribution import Distributor
from hackathon_backend.workflows.go_work import WorkflowError, require_event
from hackathon_backend.workflows.ports import AttachmentSource


class PreflightAttachments:
    def __init__(self, source: AttachmentSource) -> None:
        self.source = source
        self.prepared: ContextVar[tuple | None] = ContextVar("event_attachments", default=None)

    async def current_attachments(self, owner_id: str, event) -> list[tuple[str, str, bytes]]:
        prepared = self.prepared.get()
        if prepared is None or prepared[:3] != (owner_id, event.id, event.revision):
            raise WorkflowError("revision_conflict", "Attachment preflight no longer matches event")
        return list(prepared[3])


class PersistentDistributor(Distributor):
    def __init__(self, store, calendar, gmail, tokens, attachments: AttachmentSource) -> None:
        self.preflight = PreflightAttachments(attachments)
        super().__init__(store, calendar, gmail, tokens, self.preflight)

    async def preview(self, owner_id: str, event_id: str):
        plan = await super().preview(owner_id, event_id)
        event = await require_event(self.store, owner_id, event_id)
        if event.revision != plan.event_revision:
            raise WorkflowError("revision_conflict", "Event changed during distribution preview")
        try:
            files = await self.preflight.source.current_attachments(owner_id, event)
            if not files:
                raise WorkflowError("needs_review", "Required reviewed event assets are missing")
        except WorkflowError as error:
            plan.blockers.append(f"{error.code}: {error}")
        return plan

    async def execute(self, owner_id: str, event_id: str, approval_id: str):
        event = await require_event(self.store, owner_id, event_id)
        files = await self.preflight.source.current_attachments(owner_id, event)
        if not files:
            raise WorkflowError("needs_review", "Required reviewed event assets are missing")
        token = self.preflight.prepared.set((owner_id, event_id, event.revision, tuple(files)))
        try:
            return await super().execute(owner_id, event_id, approval_id)
        finally:
            self.preflight.prepared.reset(token)
