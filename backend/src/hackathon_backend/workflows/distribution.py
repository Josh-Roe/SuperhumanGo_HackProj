"""Organizer-approved publish/update across Google Calendar and Gmail.

Executor decision: the backend OAuth adapters are the single writer for Calendar and Gmail. Go
writes the prose and coordinates via MCP tools; it does not also write through its native Google
connectors, which would duplicate invites/emails and lose receipts.

Every provider step is an Operation keyed by event/revision(/content), so a retry after any crash
reuses the recorded result or reconciles provider state instead of repeating the write.

Unknown outcomes (A14): a Gmail step that failed without proof of no effect, or any step left
`running` by a dead worker, is read back from the provider before another attempt. If the effect
happened, its receipt is adopted; if it provably did not, the step is retried once; otherwise the
step stays blocked as `needs_review`. Nothing is ever retried blindly.
"""

import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel

from hackathon_backend.providers.google.calendar import calendar_body, deterministic_event_id
from hackathon_backend.providers.google.mime import build_message
from hackathon_backend.workflows.go_work import WorkflowError, require_event
from hackathon_backend.workflows.models import (
    NO_EFFECT_CODES,
    Approval,
    CalendarBinding,
    ContentKind,
    EventSnapshot,
    GeneratedContent,
    GmailBinding,
    Operation,
    OperationKind,
    utcnow,
)
from hackathon_backend.workflows.ports import (
    AttachmentSource,
    CalendarAPI,
    GmailAPI,
    GoogleTokenSource,
    IntegrationNotConnected,
    ProviderError,
    WorkflowStore,
)

CALENDAR_ID = "primary"
SENDING_ACTIONS = {"publish", "update"}
APPROVAL_ACTIONS = SENDING_ACTIONS | {"draft_only"}
# A live attempt is bounded by Google's 15 s request timeout (a few calls per step), so a step
# still `running` after this long belongs to a dead worker and may be read back and taken over.
STALE_RUNNING_AFTER = timedelta(minutes=2)

# (outcome, receipt) for store.reconcile_operation; None means the read-back proved nothing.
ReadBack = tuple[str, dict[str, Any]] | None


class AttachmentPolicy(Protocol):
    """Decides whether an event's invitation must carry its current reviewed flyer/document."""

    async def requires_attachments(self, owner_id: str, event: EventSnapshot) -> bool: ...


class DistributionPlan(BaseModel):
    event_id: str
    event_revision: int
    calendar_action: str  # "create" | "update"
    calendar_event_id: str | None
    gmail_action: str  # "create_draft" | "replace_draft" | "new_change_notice"
    required_content_kind: ContentKind
    invitee_count: int
    blockers: list[str]


class DistributionResult(BaseModel):
    event_id: str
    event_revision: int
    operations: list[Operation]
    calendar_link: str | None
    sent: bool


class Distributor:
    def __init__(
        self,
        store: WorkflowStore,
        calendar: CalendarAPI,
        gmail: GmailAPI,
        tokens: GoogleTokenSource,
        attachments: AttachmentSource | None = None,
        attachment_policy: AttachmentPolicy | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.store = store
        self.clock = clock
        self.calendar = calendar
        self.gmail = gmail
        self.tokens = tokens
        self.attachments = attachments
        # None keeps the original behavior: attach whatever the source returns, never block.
        self.attachment_policy = attachment_policy

    async def preview(self, owner_id: str, event_id: str) -> DistributionPlan:
        event = await require_event(self.store, owner_id, event_id)
        cal = await self.store.get_calendar_binding(owner_id, event_id)
        mail = await self.store.get_gmail_binding(owner_id, event_id)
        kind = ContentKind.CHANGE_NOTICE if mail and mail.sent else ContentKind.INVITATION
        if mail is None:
            gmail_action = "create_draft"
        elif mail.sent:
            gmail_action = "new_change_notice"
        else:
            gmail_action = "replace_draft"
        blockers = []
        content = await self.store.latest_content(owner_id, event_id, event.revision, kind)
        if content is None:
            blockers.append(f"awaiting_go: no {kind.value} for revision {event.revision}")
        elif content.state != "ready":
            blockers.append(f"needs_review: organizer has not approved the {kind.value}")
        if not event.invitees:
            blockers.append("needs_review: no invitees")
        try:
            await self._required_attachments(owner_id, event)
        except WorkflowError as missing:
            blockers.append(str(missing))
        return DistributionPlan(
            event_id=event_id,
            event_revision=event.revision,
            calendar_action="update" if cal else "create",
            calendar_event_id=cal.remote_event_id if cal else None,
            gmail_action=gmail_action,
            required_content_kind=kind,
            invitee_count=len(event.invitees),
            blockers=blockers,
        )

    async def execute(self, owner_id: str, event_id: str, approval_id: str) -> DistributionResult:
        event = await require_event(self.store, owner_id, event_id)
        approval = await self.store.get_approval(owner_id, approval_id)
        if approval is None or approval.event_id != event_id:
            raise WorkflowError("forbidden", "approval not found for this event")
        if approval.action not in APPROVAL_ACTIONS:
            raise WorkflowError("needs_review", f"unknown approval action {approval.action}")
        if approval.event_revision != event.revision:
            raise WorkflowError(
                "revision_conflict",
                f"approval is for revision {approval.event_revision}; event is {event.revision}",
            )
        # Required flyer/document must exist and be deliverable before any Calendar invitation:
        # learning it is missing inside Gmail MIME construction would leave invites already sent.
        await self._required_attachments(owner_id, event)
        try:
            # Reconcile first: a draft the organizer sent by hand in Gmail changes what is allowed.
            await self._reconcile_gmail(
                owner_id, await self.store.get_gmail_binding(owner_id, event_id)
            )
        except ProviderError as failure:
            raise WorkflowError("provider_failed", f"gmail reconcile: {failure}") from None
        except IntegrationNotConnected as missing:
            raise WorkflowError("integration_not_connected", str(missing)) from None
        content = await self._approved_content(owner_id, event, approval)
        try:
            ops = []
            calendar_op = await self._calendar(owner_id, event, approval)
            ops.append(calendar_op)
            draft_op = await self._draft(owner_id, event, approval, content, calendar_op)
            ops.append(draft_op)
            if approval.action in SENDING_ACTIONS:
                ops.append(await self._send(owner_id, event, approval, content))
        except IntegrationNotConnected as missing:
            raise WorkflowError("integration_not_connected", str(missing)) from None
        binding = await self.store.get_gmail_binding(owner_id, event_id)
        return DistributionResult(
            event_id=event_id,
            event_revision=event.revision,
            operations=ops,
            calendar_link=calendar_op.receipt.get("html_link"),
            sent=bool(binding and binding.sent and binding.content_id == content.id),
        )

    async def _requires_attachments(self, owner_id: str, event: EventSnapshot) -> bool:
        if self.attachment_policy is None:
            return False
        return await self.attachment_policy.requires_attachments(owner_id, event)

    async def _required_attachments(
        self, owner_id: str, event: EventSnapshot
    ) -> list[tuple[str, str, bytes]]:
        """Load required current-revision attachments or raise a WorkflowError blocker.

        Read-only: no provider or store writes, so preview and the execute preflight are safe.
        """
        if not await self._requires_attachments(owner_id, event):
            return []
        if self.attachments is None:
            raise WorkflowError(
                "integration_not_connected",
                "this event requires its flyer, but asset Storage is not configured",
            )
        try:
            files = await self.attachments.current_attachments(owner_id, event)
        except WorkflowError:
            raise
        except Exception as failure:
            code = getattr(failure, "code", None)
            if code in {"forbidden", "revision_conflict", "needs_review", "provider_failed"}:
                raise WorkflowError(code, str(failure)) from None
            raise WorkflowError(
                "provider_failed", "unable to load the required event attachments"
            ) from None
        if not files:
            raise WorkflowError(
                "needs_review",
                f"a reviewed flyer for revision {event.revision} is required before invitations",
            )
        return files

    async def _approved_content(
        self, owner_id: str, event: EventSnapshot, approval: Approval
    ) -> GeneratedContent:
        content = await self.store.get_content(owner_id, approval.invitation_content_id)
        if content is None or content.event_id != event.id:
            raise WorkflowError("forbidden", "approved content not found for this event")
        if content.event_revision != event.revision:
            raise WorkflowError("revision_conflict", "approved content is for another revision")
        if content.state != "ready":
            raise WorkflowError("needs_review", "organizer has not approved this content")
        mail = await self.store.get_gmail_binding(owner_id, event.id)
        if mail and mail.sent and mail.content_id != content.id:
            if content.kind != ContentKind.CHANGE_NOTICE:
                raise WorkflowError(
                    "needs_review",
                    "invitation was already sent; approve a change_notice for this revision",
                )
        elif content.kind not in (ContentKind.INVITATION, ContentKind.CHANGE_NOTICE):
            raise WorkflowError("needs_review", "approved content is not an email")
        return content

    async def _begin(
        self,
        owner_id: str,
        event: EventSnapshot,
        approval: Approval,
        kind: OperationKind,
        key: str,
        read_back: Callable[[Operation], Awaitable[ReadBack]],
    ) -> Operation:
        op = await self.store.get_operation(owner_id, key)
        if op is None:
            op = Operation(
                event_id=event.id,
                event_revision=event.revision,
                kind=kind,
                idempotency_key=key,
                approval_id=approval.id,
            )
        if op.state == "succeeded":
            return op
        if self._outcome_unknown(op):
            try:
                rejected = _rejected_status(op.error_code)
                found = (
                    ("not_applied", {"read_back": f"provider_rejected:{rejected}"})
                    if rejected
                    else await read_back(op)
                )
            except ProviderError as failure:
                raise WorkflowError(
                    "provider_failed", f"{kind.value} read-back: {failure}"
                ) from None
            if found is None:
                raise WorkflowError(
                    "needs_review",
                    f"{kind.value} outcome is unknown and provider read-back cannot prove it; "
                    "check Gmail/Calendar before retrying",
                )
            outcome, receipt = found
            op = await self.store.reconcile_operation(owner_id, key, op.attempts, outcome, receipt)
            if op.state == "succeeded":
                return op
        op = op.model_copy(
            update={"state": "running", "attempts": op.attempts + 1, "updated_at": self.clock()}
        )
        await self.store.put_operation(owner_id, op)
        return op

    def _outcome_unknown(self, op: Operation) -> bool:
        if op.state == "running":
            if self.clock() - op.updated_at < STALE_RUNNING_AFTER:
                raise WorkflowError("operation_in_progress", f"{op.kind.value} is running")
            return True  # its worker died mid-step
        return (
            op.state == "failed"
            and op.kind in (OperationKind.GMAIL_DRAFT, OperationKind.GMAIL_SEND)
            and (op.error_code or "") not in NO_EFFECT_CODES
        )

    async def _finish(
        self, owner_id: str, op: Operation, receipt: dict[str, Any] | None, error: str | None
    ) -> Operation:
        update: dict[str, Any] = {"updated_at": self.clock()}
        if error:
            update |= {"state": "failed", "error_code": error}
        else:
            update |= {"state": "succeeded", "error_code": None, "receipt": receipt or {}}
        done = op.model_copy(update=update)
        await self.store.put_operation(owner_id, done)
        return done

    async def _guard(self, owner_id: str, op: Operation, action):
        try:
            return await self._finish(owner_id, op, await action(), None)
        except ProviderError as failure:
            await self._finish(owner_id, op, None, f"provider_failed:{failure.status}")
            raise WorkflowError("provider_failed", f"{op.kind.value}: {failure}") from None
        except IntegrationNotConnected:
            await self._finish(owner_id, op, None, "integration_not_connected")
            raise
        except WorkflowError:
            # Only raised by our own checks (e.g. required attachments) before any provider
            # write in this step, so a retry is safe without provider reconciliation.
            await self._finish(owner_id, op, None, "confirmed_no_effect")
            raise

    # Calendar -----------------------------------------------------------------------------

    async def _calendar(self, owner_id: str, event: EventSnapshot, approval: Approval):
        key = f"{event.id}:{event.revision}:{OperationKind.CALENDAR_UPSERT.value}"

        async def read_back(_: Operation) -> ReadBack:
            binding = await self.store.get_calendar_binding(owner_id, event.id)
            remote_id = (
                binding.remote_event_id if binding else deterministic_event_id("evt", event.id)
            )
            try:
                remote = await self.calendar.get_event(owner_id, CALENDAR_ID, remote_id)
            except ProviderError as missing:
                if missing.status != 404:
                    raise
                return "not_applied", {"calendar_event_id": remote_id, "read_back": "absent"}
            if _remote_revision(remote) != event.revision:
                return "not_applied", {
                    "calendar_event_id": remote_id,
                    "read_back": f"remote_revision_{_remote_revision(remote)}",
                }
            return "succeeded", await self._bind_calendar(owner_id, event, remote_id, remote)

        op = await self._begin(
            owner_id, event, approval, OperationKind.CALENDAR_UPSERT, key, read_back
        )
        if op.state == "succeeded":
            return op
        return await self._guard(owner_id, op, lambda: self._upsert_calendar(owner_id, event))

    async def _upsert_calendar(self, owner_id: str, event: EventSnapshot) -> dict[str, Any]:
        description = await self.store.latest_content(
            owner_id, event.id, event.revision, ContentKind.DESCRIPTION
        )
        text = description.body if description and description.state == "ready" else ""
        body = calendar_body(event, text or event.description)
        binding = await self.store.get_calendar_binding(owner_id, event.id)
        remote_id = binding.remote_event_id if binding else deterministic_event_id("evt", event.id)
        if binding is None:
            try:
                await self.calendar.insert_event(
                    owner_id, CALENDAR_ID, {**body, "id": remote_id}, "all"
                )
            except ProviderError as exists:
                if exists.status != 409:
                    raise
                # A prior attempt created it before its binding was saved: adopt, don't duplicate.
                binding = CalendarBinding(
                    event_id=event.id, remote_event_id=remote_id, event_revision=0
                )
        if binding is not None:
            remote = await self.calendar.get_event(owner_id, CALENDAR_ID, remote_id)
            if _remote_revision(remote) != event.revision:
                try:
                    await self.calendar.patch_event(
                        owner_id, CALENDAR_ID, remote_id, body, "all", remote.get("etag")
                    )
                except ProviderError as stale:
                    if stale.status != 412:
                        raise
                    remote = await self.calendar.get_event(owner_id, CALENDAR_ID, remote_id)
                    await self.calendar.patch_event(
                        owner_id, CALENDAR_ID, remote_id, body, "all", remote.get("etag")
                    )
        remote = await self.calendar.get_event(owner_id, CALENDAR_ID, remote_id)  # read back
        if _remote_revision(remote) != event.revision:
            raise ProviderError(409, "Calendar read-back does not match the approved revision")
        return await self._bind_calendar(owner_id, event, remote_id, remote)

    async def _bind_calendar(
        self, owner_id: str, event: EventSnapshot, remote_id: str, remote: dict[str, Any]
    ) -> dict[str, Any]:
        await self.store.put_calendar_binding(
            owner_id,
            CalendarBinding(
                event_id=event.id,
                calendar_id=CALENDAR_ID,
                remote_event_id=remote_id,
                html_link=remote.get("htmlLink"),
                etag=remote.get("etag"),
                event_revision=event.revision,
            ),
        )
        return {
            "calendar_event_id": remote_id,
            "html_link": remote.get("htmlLink"),
            "etag": remote.get("etag"),
            "updated": remote.get("updated"),
        }

    # Gmail --------------------------------------------------------------------------------

    async def _reconcile_gmail(self, owner_id: str, binding: GmailBinding | None):
        """A missing draft is not proof of sending: check the underlying message's labels."""
        if binding is None or binding.sent or binding.draft_id is None:
            return binding
        if await self.gmail.get_draft(owner_id, binding.draft_id) is not None:
            return binding
        message = (
            await self.gmail.get_message(owner_id, binding.message_id)
            if binding.message_id
            else None
        )
        if message and "SENT" in message.get("labelIds", []):
            binding = _mark_sent(binding, message)
        else:
            binding = binding.model_copy(update={"draft_id": None, "message_id": None})
        await self.store.put_gmail_binding(owner_id, binding)
        return binding

    async def _draft(
        self,
        owner_id: str,
        event: EventSnapshot,
        approval: Approval,
        content: GeneratedContent,
        calendar_op: Operation,
    ) -> Operation:
        key = f"{event.id}:{event.revision}:{content.id}:{OperationKind.GMAIL_DRAFT.value}"

        async def read_back(_: Operation) -> ReadBack:
            sender = await self.tokens.account_email(owner_id)
            binding = await self._reconcile_gmail(
                owner_id, await self.store.get_gmail_binding(owner_id, event.id)
            )
            if binding and binding.content_id == content.id and (binding.draft_id or binding.sent):
                return "succeeded", {**_draft_receipt(binding), "read_back": "binding"}
            found = await self.gmail.find_by_message_id(
                owner_id, _message_id(event, content, sender)
            )
            drafts = [item for item in found if item.get("draft_id")]
            if len(found) != 1 or len(drafts) != 1:
                return None  # absent from search is not proof; several copies need a human
            adopted = _content_binding(event, content, binding, drafts[0])
            await self.store.put_gmail_binding(owner_id, adopted)
            return "succeeded", {**_draft_receipt(adopted), "read_back": "message_id_search"}

        op = await self._begin(owner_id, event, approval, OperationKind.GMAIL_DRAFT, key, read_back)
        if op.state == "succeeded":
            return op

        async def write() -> dict[str, Any]:
            binding = await self._reconcile_gmail(
                owner_id, await self.store.get_gmail_binding(owner_id, event.id)
            )
            raw = await self._mime(owner_id, event, content, calendar_op.receipt.get("html_link"))
            thread_id = binding.thread_id if binding else None
            draft = None
            if binding and not binding.sent and binding.draft_id:
                try:
                    draft = await self.gmail.update_draft(
                        owner_id, binding.draft_id, raw, thread_id
                    )
                except ProviderError as gone:
                    if gone.status != 404:
                        raise
                    binding = await self._reconcile_gmail(owner_id, binding)
            if draft is None:
                draft = await self.gmail.create_draft(owner_id, raw, thread_id)
            message = draft.get("message", {})
            updated = _content_binding(
                event,
                content,
                binding,
                {
                    "draft_id": draft["id"],
                    "id": message.get("id"),
                    "threadId": message.get("threadId") or thread_id,
                },
            )
            await self.store.put_gmail_binding(owner_id, updated)
            return {
                **_draft_receipt(updated),
                "replaced_unsent_draft": bool(binding and not binding.sent and binding.draft_id),
            }

        return await self._guard(owner_id, op, write)

    async def _send(
        self, owner_id: str, event: EventSnapshot, approval: Approval, content: GeneratedContent
    ) -> Operation:
        key = f"{event.id}:{event.revision}:{content.id}:{OperationKind.GMAIL_SEND.value}"

        async def read_back(_: Operation) -> ReadBack:
            sender = await self.tokens.account_email(owner_id)
            stored = await self.store.get_gmail_binding(owner_id, event.id)
            binding = await self._reconcile_gmail(owner_id, stored)
            if binding is None or binding.content_id != content.id:
                return None
            if binding.sent:
                return "succeeded", {**_sent_receipt(binding), "read_back": "sent_label"}
            if binding.draft_id:  # _reconcile_gmail just saw the draft: Gmail removes it on send
                return "not_applied", {"draft_id": binding.draft_id, "read_back": "draft_unsent"}
            # The draft vanished and its message ID shows no SENT copy; search the header too.
            found = await self.gmail.find_by_message_id(
                owner_id, _message_id(event, content, sender)
            )
            sent = [item for item in found if "SENT" in item.get("labelIds", [])]
            if len(sent) != 1:
                return None
            binding = _mark_sent(binding, sent[0])
            await self.store.put_gmail_binding(owner_id, binding)
            return "succeeded", {**_sent_receipt(binding), "read_back": "message_id_search"}

        op = await self._begin(owner_id, event, approval, OperationKind.GMAIL_SEND, key, read_back)
        if op.state == "succeeded":
            return op

        async def send() -> dict[str, Any]:
            binding = await self._reconcile_gmail(
                owner_id, await self.store.get_gmail_binding(owner_id, event.id)
            )
            if binding is None or binding.content_id != content.id:
                raise ProviderError(409, "Gmail draft does not hold the approved content")
            if not binding.sent:  # otherwise an earlier attempt already sent before crashing
                message = await self.gmail.send_draft(owner_id, binding.draft_id or "")
                binding = _mark_sent(binding, message)
                await self.store.put_gmail_binding(owner_id, binding)
            return _sent_receipt(binding)

        return await self._guard(owner_id, op, send)

    async def _mime(
        self,
        owner_id: str,
        event: EventSnapshot,
        content: GeneratedContent,
        calendar_link: str | None,
    ) -> bytes:
        sender = await self.tokens.account_email(owner_id)
        details = [content.body.rstrip(), ""]
        if calendar_link:
            details.append(f"Calendar invitation: {calendar_link}")
        details += [f"Link: {link}" for link in event.links]
        details += ["", f"Questions? Contact the organizer: {event.organizer_contact}"]
        if self.attachment_policy is not None:
            # Policy-governed: required files are rechecked here (event may have moved since
            # preflight); events that do not require them carry none.
            files = await self._required_attachments(owner_id, event)
        else:
            files = (
                await self.attachments.current_attachments(owner_id, event)
                if self.attachments
                else []
            )
        return build_message(
            sender=sender,
            to=[sender],  # invitees are Bcc so addresses are not exposed to each other
            bcc=[invitee.email for invitee in event.invitees],
            subject=content.subject or event.title,
            text_body="\n".join(details) + "\n",
            attachments=files,
            headers={
                "X-Event-Revision": f"{event.id}/{event.revision}",
                # Deterministic so an unknown draft-create outcome can be found again by header.
                "Message-ID": _message_id(event, content, sender),
            },
        )


def _message_id(event: EventSnapshot, content: GeneratedContent, sender: str) -> str:
    def clean(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9.-]", "-", value)

    domain = clean(sender.rpartition("@")[2]) or "invalid"
    return f"<evt-{clean(event.id)}-r{event.revision}-{clean(content.id)}@{domain}>"


def _rejected_status(error_code: str | None) -> int | None:
    """A definite 4xx answer (not a timeout) means Google refused the write: no effect."""
    status = (error_code or "").removeprefix("provider_failed:")
    if status.isdigit() and 400 <= int(status) < 500 and int(status) != 408:
        return int(status)
    return None


def _content_binding(
    event: EventSnapshot,
    content: GeneratedContent,
    previous: GmailBinding | None,
    message: dict[str, Any],
) -> GmailBinding:
    return GmailBinding(
        event_id=event.id,
        draft_id=message.get("draft_id"),
        message_id=message.get("id"),
        thread_id=message.get("threadId") or (previous.thread_id if previous else None),
        sent=False,
        event_revision=event.revision,
        content_id=content.id,
        sent_history=previous.sent_history if previous else [],
    )


def _draft_receipt(binding: GmailBinding) -> dict[str, Any]:
    return {
        "draft_id": binding.draft_id,
        "message_id": binding.message_id,
        "thread_id": binding.thread_id,
    }


def _sent_receipt(binding: GmailBinding) -> dict[str, Any]:
    return {"message_id": binding.message_id, "thread_id": binding.thread_id}


def _remote_revision(remote: dict[str, Any]) -> int:
    private = remote.get("extendedProperties", {}).get("private", {})
    try:
        return int(private.get("app_revision", 0))
    except ValueError:
        return 0


def _mark_sent(binding: GmailBinding, message: dict[str, Any]) -> GmailBinding:
    entry = {
        "message_id": message.get("id"),
        "thread_id": message.get("threadId"),
        "event_revision": binding.event_revision,
        "content_id": binding.content_id,
        "sent_at": utcnow().isoformat(),
    }
    return binding.model_copy(
        update={
            "sent": True,
            "draft_id": None,
            "message_id": message.get("id"),
            "thread_id": message.get("threadId") or binding.thread_id,
            "sent_history": [*binding.sent_history, entry],
        }
    )
