"""Member 3 composition of Member 4's asset services: Go prose → document/inclusion → Canva flyer.

`register_asset_services(app, mcp, settings, events)` is called by `main.py` in Supabase mode. It
wires `EventAssetPreparationService` over the shared `WorkflowStore` plus Member 2's private
`SupabaseAssetStorage`, a vault-held Canva MCP session, and Member 4's guarded attachment reader
into the Distributor, then registers:

- Go MCP tools (connector-token principal): read asset status, queue asset prose, render the
  event document, start/poll/preview/export the custom Canva flyer. Go never approves.
- Organizer REST routes (Supabase session): the same actions plus private inclusion review
  (with Google public holiday calendars checked for religious-observance conflicts),
  organizer approval of the exact flyer preview, and abandoning a flyer.

Fail closed: no Canva token → `integration_not_connected`; nothing reports success it lacks.
Canva create is never retried blindly: an interrupted create stays `creating` until the
organizer reconciles in Canva and abandons it. Flyer state (including Canva's continuation
token) is kept per event in the durable, encrypted `canva_flyer_jobs` table, and every flyer
action holds that table's fenced cross-process lease (in-memory store/lock in tests and dev).
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import uuid4

import httpx
from fastapi import APIRouter, FastAPI, Header
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, ValidationError
from starlette.responses import JSONResponse
from starlette.routing import Mount

from hackathon_backend.config import Settings
from hackathon_backend.mcp_tools.event_tools import EventToolDeps, principal
from hackathon_backend.providers.canva import (
    CanvaError,
    CanvaMCPAdapter,
    CreationJob,
    ExportReceipt,
    FlyerReviewPreview,
    VerifiedDesign,
)
from hackathon_backend.services.assets.models import Approval as FlyerApproval
from hackathon_backend.services.assets.models import DesignRef, StaleRevisionError
from hackathon_backend.services.assets.models import EventSnapshot as AssetEvent
from hackathon_backend.services.assets.preparation import EventAssetPreparationService
from hackathon_backend.services.assets.storage import AssetStorage, ExportDownloader
from hackathon_backend.services.inclusion import HolidayCalendar, InclusionInput
from hackathon_backend.workflows.go_work import WorkflowError, require_event
from hackathon_backend.workflows.models import EventSnapshot
from hackathon_backend.workflows.ports import WorkflowStore

FlyerStage = Literal[
    "creating",  # create claimed; no provider job recorded yet (uncertain if interrupted)
    "pending",  # Canva creation job running
    "created",  # design exists; needs preview + organizer approval
    "previewed",
    "approved",  # organizer approved the exact preview; text verified
    "exporting",  # export job pending
    "stored",  # PNG export saved to private Storage at this revision
    "failed",
    "abandoned",  # organizer opted out; invitations no longer require the flyer
]
ACTIVE_STAGES = {"creating", "pending", "created", "previewed", "approved", "exporting", "stored"}
CANVA_SECRET = "canva"  # vault record {"access_token": ...} placed by an authorized OAuth flow
FLYER_SECRET_PREFIX = "canva_flyer:"


def _now() -> datetime:
    return datetime.now(UTC)


# Persistent per-event flyer state ----------------------------------------------------------


class FlyerState(BaseModel):
    event_id: str
    event_revision: int
    stage: FlyerStage
    generation_ids: dict[str, str] = {}
    job: dict[str, Any] | None = None
    continuation_token: str | None = Field(default=None, repr=False)  # server-only
    design: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    verified: dict[str, Any] | None = None
    export: dict[str, Any] | None = None
    asset: dict[str, Any] | None = None
    failure_code: str | None = None
    history: list[dict[str, Any]] = []
    updated_at: datetime = Field(default_factory=_now)

    def public(self) -> dict[str, Any]:
        """Organizer/Go-safe view: no continuation token, signed URLs or Storage keys."""
        job = self.job or {}
        return {
            "event_id": self.event_id,
            "event_revision": self.event_revision,
            "stage": self.stage,
            "failure_code": self.failure_code,
            "generation_ids": self.generation_ids,
            "job": {
                key: job.get(key)
                for key in ("job_id", "state", "next_poll_at", "polling_instructions")
            }
            if self.job
            else None,
            "design": {
                key: self.design.get(key) for key in ("design_id", "edit_url", "view_url")
            }
            if self.design
            else None,
            "preview": {
                "digest": self.preview["digest"],
                "expected": self.preview["expected"],
                "thumbnail_urls": self.preview["thumbnail_urls"],
            }
            if self.preview
            else None,
            "verified": {
                key: self.verified.get(key)
                for key in ("state", "missing_roles", "stale_roles", "organizer_reviewed")
            }
            if self.verified
            else None,
            "export": self.export,
            "asset": self.asset,
            "prior_attempts": len(self.history),
        }

    def pending_approval(self, current_revision: int) -> dict[str, Any] | None:
        """A9: the Canva operation awaiting organizer approval, or None.

        Only a preview of the current event revision is approvable; Canva thumbnail URLs are
        short-lived, so re-preview (which yields a new digest) when they stop loading.
        """
        if self.stage != "previewed" or not self.preview or self.event_revision != current_revision:
            return None
        return {
            "operation_id": (self.job or {}).get("job_id"),
            "design_id": (self.design or {}).get("design_id"),
            "event_revision": self.event_revision,
            "digest": self.preview["digest"],
            "thumbnail_urls": self.preview["thumbnail_urls"],
            "approve": {
                "method": "POST",
                "path": f"/api/events/{self.event_id}/assets/flyer/approve",
                "body": {
                    "expected_revision": self.event_revision,
                    "preview_digest": self.preview["digest"],
                },
            },
        }

    def archived(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"continuation_token", "history"})


class FlyerStateStore(Protocol):
    async def get(self, owner_id: str, event_id: str) -> FlyerState | None: ...

    async def put(self, owner_id: str, state: FlyerState) -> None: ...

    def lease(self, owner_id: str, event_id: str) -> Any:
        """Async context manager: exclusive flyer-write lease for one event."""
        ...


LEASE_TTL_SECONDS = 300  # longer than one Canva call (read timeout 300 s); expires on crash
LEASE_ATTEMPTS = 20
LEASE_RETRY_SECONDS = 0.5


class ProcessLeases:
    """Per-process lock per event: tests, dev and the single-instance legacy vault store."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    @asynccontextmanager
    async def lease(self, owner_id: str, event_id: str) -> AsyncIterator[None]:
        async with self._locks.setdefault((owner_id, event_id), asyncio.Lock()):
            yield


class MemoryFlyerStateStore(ProcessLeases):
    """Tests/dev only; state is lost on restart."""

    def __init__(self) -> None:
        super().__init__()
        self.states: dict[tuple[str, str], FlyerState] = {}

    async def get(self, owner_id: str, event_id: str) -> FlyerState | None:
        return self.states.get((owner_id, event_id))

    async def put(self, owner_id: str, state: FlyerState) -> None:
        self.states[(owner_id, state.event_id)] = state


class SecretVault(Protocol):
    async def put_secret(self, owner_id: str, provider: str, value: dict) -> None: ...

    async def get_secret(self, owner_id: str, provider: str) -> dict | None: ...


class VaultFlyerStateStore(ProcessLeases):
    """Legacy: encrypted vault records, process-local lock. Read as a fallback by the durable
    store for flyers started before `canva_flyer_jobs` existed."""

    def __init__(self, vault: SecretVault) -> None:
        super().__init__()
        self.vault = vault

    async def get(self, owner_id: str, event_id: str) -> FlyerState | None:
        raw = await self.vault.get_secret(owner_id, FLYER_SECRET_PREFIX + event_id)
        return FlyerState.model_validate(raw) if raw else None

    async def put(self, owner_id: str, state: FlyerState) -> None:
        await self.vault.put_secret(
            owner_id, FLYER_SECRET_PREFIX + state.event_id, state.model_dump(mode="json")
        )


class SupabaseFlyerStateStore:
    """Durable flyer job state in `canva_flyer_jobs` (migration 20261017030000), server-only.

    State is Fernet-encrypted with CREDENTIAL_ENCRYPTION_KEY and bound to owner/event because it
    holds Canva's continuation token. Writes are fenced by an expiring lease row: only the
    current holder can save, a crashed holder's lease expires after LEASE_TTL_SECONDS, and a
    busy lease reports operation_in_progress instead of running a second Canva action.
    """

    def __init__(
        self,
        database: Any,
        encryption_key: str,
        *,
        legacy: FlyerStateStore | None = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        from cryptography.fernet import Fernet

        self.db = database
        self._cipher = Fernet(encryption_key.encode())
        self.legacy = legacy
        self._sleep = sleep
        self._holders: dict[tuple[str, str], str] = {}
        self._local = ProcessLeases()

    async def get(self, owner_id: str, event_id: str) -> FlyerState | None:
        from cryptography.fernet import InvalidToken

        rows = await self.db.rows(
            "canva_flyer_jobs",
            select="ciphertext",
            owner_id=f"eq.{owner_id}",
            event_id=f"eq.{event_id}",
        )
        ciphertext = rows[0].get("ciphertext") if rows else None
        if not ciphertext:
            return await self.legacy.get(owner_id, event_id) if self.legacy else None
        try:
            envelope = json.loads(self._cipher.decrypt(ciphertext.encode()))
            if envelope["owner_id"] != owner_id or envelope["event_id"] != event_id:
                raise ValueError("scope mismatch")
            return FlyerState.model_validate(envelope["state"])
        except (InvalidToken, ValueError, KeyError, TypeError):
            raise WorkflowError("provider_failed", "flyer job state is unreadable") from None

    async def put(self, owner_id: str, state: FlyerState) -> None:
        holder = self._holders.get((owner_id, state.event_id))
        if holder is None:
            raise WorkflowError("operation_in_progress", "flyer state written without a lease")
        envelope = {
            "owner_id": owner_id,
            "event_id": state.event_id,
            "state": state.model_dump(mode="json"),
        }
        await self.db.rpc(
            "canva_flyer_save",
            p_owner=owner_id,
            p_event=state.event_id,
            p_holder=holder,
            p_event_revision=state.event_revision,
            p_stage=state.stage,
            p_ciphertext=self._cipher.encrypt(json.dumps(envelope).encode()).decode(),
        )

    @asynccontextmanager
    async def lease(self, owner_id: str, event_id: str) -> AsyncIterator[None]:
        key = (owner_id, event_id)
        async with self._local.lease(owner_id, event_id):  # no DB spinning within one process
            holder = uuid4().hex
            for attempt in range(LEASE_ATTEMPTS):
                if await self.db.rpc(
                    "canva_flyer_acquire",
                    p_owner=owner_id,
                    p_event=event_id,
                    p_holder=holder,
                    p_ttl_seconds=LEASE_TTL_SECONDS,
                ):
                    break
                if attempt < LEASE_ATTEMPTS - 1:
                    await self._sleep(LEASE_RETRY_SECONDS)
            else:
                raise WorkflowError(
                    "operation_in_progress", "another flyer action is running; retry shortly"
                )
            self._holders[key] = holder
            try:
                yield
            finally:
                self._holders.pop(key, None)
                try:
                    await self.db.rpc(
                        "canva_flyer_release", p_owner=owner_id, p_event=event_id, p_holder=holder
                    )
                except Exception:  # noqa: BLE001 - an unreleased lease expires on its own
                    pass


# Canva sessions ---------------------------------------------------------------------------


class CanvaScopedSession(Protocol):
    def capabilities(self) -> Any: ...

    def adapter(self, *, owner_id: str) -> CanvaMCPAdapter: ...


class CanvaSessions(Protocol):
    async def connected(self, owner_id: str) -> bool: ...

    def open(self, owner_id: str) -> Any:
        """Async context manager yielding a discovered, owner-bound Canva session."""
        ...


class VaultCanvaSessions:
    """Opens Canva's remote MCP with the organizer's server-held access token.

    No token → integration_not_connected. With `tokens` (Canva Connect OAuth, see
    `workflows/canva_connect.py`) an expiring access token is refreshed first; a rejected
    refresh also reports integration_not_connected so the organizer reconnects.
    """

    def __init__(
        self,
        vault: SecretVault,
        connect: Callable[..., Any] | None = None,
        tokens: Any | None = None,
    ) -> None:
        if connect is None:
            from hackathon_backend.providers.canva.session import connect_canva

            connect = connect_canva
        self.vault = vault
        self._connect = connect
        self._tokens = tokens

    async def _token(self, owner_id: str) -> str | None:
        if self._tokens is not None:
            try:
                return await self._tokens.access_token(owner_id)
            except CanvaError:
                raise WorkflowError(
                    "integration_not_connected", "Canva authorization expired; reconnect Canva"
                ) from None
        record = await self.vault.get_secret(owner_id, CANVA_SECRET)
        token = (record or {}).get("access_token")
        return token if isinstance(token, str) and token else None

    async def connected(self, owner_id: str) -> bool:
        if self._tokens is not None:
            return await self._tokens.connected(owner_id)
        return await self._token(owner_id) is not None

    @asynccontextmanager
    async def open(self, owner_id: str) -> AsyncIterator[CanvaScopedSession]:
        token = await self._token(owner_id)
        if token is None:
            raise WorkflowError(
                "integration_not_connected", "Canva is not connected for this organizer"
            )
        async with self._connect(owner_id=owner_id, access_token=token) as session:
            yield session


# Attachments for the Distributor ---------------------------------------------------------


class FlyerRequiredPolicy:
    """An event requires its reviewed current-revision flyer once the organizer started one.

    Abandoning the flyer (organizer action) lifts the requirement; never-started events publish
    without attachments exactly as before.
    """

    def __init__(self, flyers: FlyerStateStore) -> None:
        self.flyers = flyers

    async def requires_attachments(self, owner_id: str, event: EventSnapshot) -> bool:
        state = await self.flyers.get(owner_id, event.id)
        return state is not None and state.stage != "abandoned"


class OwnerScopedAttachments:
    """Member 4's guarded `RevisionedAttachmentSource` over Member 2's Storage, per organizer.

    Builds the owner-bound Storage/read bridge for each call with a dedicated unauthenticated
    HTTP client for signed-object downloads. Errors surface as WorkflowError codes.
    """

    def __init__(
        self,
        storage_for: Callable[[str], Any],
        storage_origin: str,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.storage_for = storage_for
        self.storage_origin = storage_origin
        self.client_factory = client_factory or _download_client

    async def current_attachments(
        self, owner_id: str, event: EventSnapshot
    ) -> list[tuple[str, str, bytes]]:
        from hackathon_backend.services.assets.attachments import RevisionedAttachmentSource
        from hackathon_backend.services.assets.supabase_read import SupabaseAttachmentRepository

        async with self.client_factory() as client:
            reader = SupabaseAttachmentRepository(
                self.storage_for(owner_id), client, storage_origin=self.storage_origin
            )
            source = RevisionedAttachmentSource(reader, error_factory=WorkflowError)
            return await source.current_attachments(owner_id, event)


def _download_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30, read=60), follow_redirects=False, trust_env=False
    )


# Coordinator ------------------------------------------------------------------------------


def _as_workflow_error(error: Exception) -> WorkflowError:
    if isinstance(error, WorkflowError):
        return error
    if isinstance(error, PermissionError):
        return WorkflowError("forbidden", "outside this organizer's event scope")
    if isinstance(error, StaleRevisionError):
        return WorkflowError("revision_conflict", "event or flyer revision changed; reload")
    if isinstance(error, CanvaError):
        code = str(error) or "canva_failed"
        if code in {"canva_required_tool_unavailable", "canva_export_poll_unavailable"}:
            return WorkflowError("integration_not_connected", f"canva: {code}")
        return WorkflowError("provider_failed", f"canva: {code}")
    if isinstance(error, ValidationError):
        return WorkflowError("needs_review", "invalid asset data")
    if isinstance(error, ValueError):
        return WorkflowError("needs_review", str(error))
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return WorkflowError(code, getattr(error, "message", "") or "request failed")
    return WorkflowError("provider_failed", "asset operation failed")


class AssetCoordinator:
    """Owner-scoped asset actions shared by Go MCP tools and organizer REST routes.

    `owner_id` always comes from a resolved principal (connector token or Supabase session).
    """

    def __init__(
        self,
        store: WorkflowStore,
        *,
        storage_for: Callable[[str], AssetStorage | None],
        canva: CanvaSessions | None,
        flyers: FlyerStateStore,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        clock: Callable[[], datetime] = _now,
        holidays: HolidayCalendar | None = None,
    ) -> None:
        self.store = store
        self.holidays = holidays
        self.storage_for = storage_for
        self.canva = canva
        self.flyers = flyers
        self.client_factory = client_factory or _download_client
        self.clock = clock

    def _prep(self, owner_id: str) -> EventAssetPreparationService:
        return EventAssetPreparationService(self.store, self.storage_for(owner_id), self.holidays)

    async def _guard(self, action: Awaitable[Any]) -> Any:
        try:
            return await action
        except Exception as error:
            raise _as_workflow_error(error) from None

    def _lock(self, owner_id: str, event_id: str) -> Any:
        # The store's lease: durable and cross-process in Supabase mode.
        return self.flyers.lease(owner_id, event_id)

    async def _event(self, owner_id: str, event_id: str, expected_revision: int) -> AssetEvent:
        batch = await self._prep(owner_id).read(owner_id, event_id, expected_revision)
        return batch.event

    @asynccontextmanager
    async def _canva(self, owner_id: str, action: str) -> AsyncIterator[CanvaMCPAdapter]:
        if self.canva is None:
            raise WorkflowError(
                "integration_not_connected", "Canva is not configured on this server"
            )
        async with self.canva.open(owner_id) as session:
            caps = session.capabilities()
            if action not in caps.available_actions:
                missing = ", ".join(caps.missing_tools) or action
                raise WorkflowError(
                    "integration_not_connected", f"Canva session lacks {action} tools: {missing}"
                )
            yield session.adapter(owner_id=owner_id)

    async def _state(self, owner_id: str, event_id: str, expected_revision: int) -> FlyerState:
        state = await self.flyers.get(owner_id, event_id)
        if state is None or state.stage == "abandoned":
            raise WorkflowError("needs_review", "no flyer has been started for this event")
        if state.event_revision != expected_revision:
            raise WorkflowError(
                "revision_conflict",
                f"flyer is for revision {state.event_revision}; start a flyer for the current one",
            )
        return state

    async def _save(self, owner_id: str, state: FlyerState, **update: Any) -> FlyerState:
        state = state.model_copy(update={**update, "updated_at": self.clock()})
        await self.flyers.put(owner_id, state)
        return state

    # Status / prose / document / inclusion ----------------------------------------------

    async def status(self, owner_id: str, event_id: str) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            event = await require_event(self.store, owner_id, event_id)
            batch = await self._prep(owner_id).read(owner_id, event_id, event.revision)
            flyer = await self.flyers.get(owner_id, event_id)
            connected = bool(self.canva) and await self.canva.connected(owner_id)
            return {
                "prose": batch.preview_metadata(),
                "flyer": flyer.public() if flyer else None,
                "flyer_stale": bool(flyer and flyer.event_revision < event.revision),
                "flyer_pending_approval": flyer.pending_approval(event.revision) if flyer else None,
                "flyer_required_for_invitations": bool(flyer and flyer.stage != "abandoned"),
                "canva": "connected" if connected else "integration_not_connected",
                "storage": "configured"
                if self.storage_for(owner_id) is not None
                else "integration_not_connected",
            }

        return await self._guard(run())

    async def request_prose(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        prep = self._prep(owner_id)
        receipt = await self._guard(prep.request_prose(owner_id, event_id, revision))
        return receipt.model_dump(mode="json", exclude={"owner_id"})

    async def prepare_document(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        result = await self._guard(
            self._prep(owner_id).prepare_document(owner_id, event_id, revision)
        )
        return result.preview_metadata()

    async def inclusion(
        self, owner_id: str, event_id: str, revision: int, facts: InclusionInput
    ) -> dict[str, Any]:
        report = await self._guard(
            self._prep(owner_id).inclusion(owner_id, event_id, revision, facts)
        )
        return report.model_dump(mode="json")

    # Canva flyer ---------------------------------------------------------------------------

    async def start_flyer(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        async with self._lock(owner_id, event_id):
            return await self._guard(self._start_flyer(owner_id, event_id, revision))

    async def _start_flyer(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        prior = await self.flyers.get(owner_id, event_id)
        if prior and prior.event_revision == revision and prior.stage in ACTIVE_STAGES:
            if prior.stage == "creating":
                raise WorkflowError(
                    "needs_review",
                    "an earlier Canva create may have run; check Canva, then abandon to retry",
                )
            return prior.public()  # idempotent: never a second design for the same revision
        batch = await self._prep(owner_id).read(owner_id, event_id, revision)
        if batch.content_for("flyer_brief") is None or batch.content_for("flyer_copy") is None:
            raise WorkflowError("awaiting_go", "Go flyer brief and displayed copy are required")
        history = [*prior.history, prior.archived()] if prior else []
        async with self._canva(owner_id, "create") as canva:
            # Claim before the provider call so an interrupted create is never blindly repeated.
            state = await self._save(
                owner_id,
                FlyerState(
                    event_id=event_id, event_revision=revision, stage="creating", history=history
                ),
            )
            try:
                created = await self._prep(owner_id).start_flyer(
                    owner_id, event_id, revision, canva
                )
            except CanvaError as error:
                await self._save(owner_id, state, failure_code=str(error))
                raise
        state = await self._record_job(owner_id, state, created.job, created.generation_ids)
        return state.public()

    async def _record_job(
        self,
        owner_id: str,
        state: FlyerState,
        job: CreationJob,
        generation_ids: dict[str, str] | None = None,
    ) -> FlyerState:
        stage = {"pending": "pending", "completed": "created", "failed": "failed"}[job.state]
        return await self._save(
            owner_id,
            state,
            stage=stage,
            job=job.model_dump(mode="json"),
            continuation_token=job.continuation_token,
            design=job.design.model_dump(mode="json") if job.design else state.design,
            generation_ids=generation_ids or state.generation_ids,
            failure_code=job.failure_code,
        )

    async def poll_flyer(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        async with self._lock(owner_id, event_id):
            return await self._guard(self._poll(owner_id, event_id, revision))

    async def _poll(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        state = await self._state(owner_id, event_id, revision)
        if state.stage != "pending":
            return state.public()
        event = await self._event(owner_id, event_id, revision)
        job = CreationJob.model_validate(
            {**(state.job or {}), "continuation_token": state.continuation_token}
        )
        async with self._canva(owner_id, "create") as canva:
            job = await canva.poll_creation(event, job, now=self.clock())
        return (await self._record_job(owner_id, state, job)).public()

    async def preview_flyer(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        async with self._lock(owner_id, event_id):
            return await self._guard(self._preview(owner_id, event_id, revision))

    async def _preview(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        state = await self._state(owner_id, event_id, revision)
        if state.stage not in {"created", "previewed", "approved"} or not state.design:
            raise WorkflowError("needs_review", f"flyer is {state.stage}; cannot preview yet")
        event = await self._event(owner_id, event_id, revision)
        async with self._canva(owner_id, "review") as canva:
            preview = await canva.preview_flyer(
                event, DesignRef.model_validate(state.design), now=self.clock()
            )
        # A fresh preview (e.g. after manual Canva edits) invalidates any earlier approval.
        state = await self._save(
            owner_id,
            state,
            stage="previewed",
            preview=preview.model_dump(mode="json"),
            verified=None,
            export=None,
            asset=None,
        )
        return state.public()

    async def approve_flyer(
        self, owner_id: str, event_id: str, revision: int, digest: str
    ) -> dict[str, Any]:
        """Organizer-only (REST). Binds approval to the exact preview digest and revision."""
        async with self._lock(owner_id, event_id):
            return await self._guard(self._approve(owner_id, event_id, revision, digest))

    async def _approve(
        self, owner_id: str, event_id: str, revision: int, digest: str
    ) -> dict[str, Any]:
        state = await self._state(owner_id, event_id, revision)
        if state.stage != "previewed" or not state.preview:
            raise WorkflowError("needs_review", "preview the flyer before approving it")
        if state.preview["digest"] != digest:
            raise WorkflowError("needs_review", "approval does not match the current preview")
        event = await self._event(owner_id, event_id, revision)
        preview = FlyerReviewPreview.model_validate(state.preview)
        approval = FlyerApproval(
            owner_id=owner_id,
            event_id=event_id,
            event_revision=revision,
            preview_digest=digest,
            approved_at=self.clock(),
            approval_id=uuid4().hex,
        )
        async with self._canva(owner_id, "review") as canva:
            verified = await canva.approve_flyer(event, preview, approval)
        if not verified.organizer_reviewed:
            await self._save(owner_id, state, verified=verified.model_dump(mode="json"))
            raise WorkflowError("needs_review", "flyer text no longer matches the event")
        state = await self._save(
            owner_id,
            state,
            stage="approved",
            verified=verified.model_dump(mode="json"),
            failure_code=None,
        )
        return state.public()

    async def export_flyer(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        async with self._lock(owner_id, event_id):
            return await self._guard(self._export(owner_id, event_id, revision))

    async def _export(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        state = await self._state(owner_id, event_id, revision)
        if state.stage == "stored":
            return state.public()  # idempotent: the stored export is immutable
        if state.stage not in {"approved", "exporting"} or not state.verified:
            raise WorkflowError("needs_review", "organizer must approve the flyer preview first")
        if self.storage_for(owner_id) is None:
            raise WorkflowError("integration_not_connected", "private asset Storage is missing")
        event = await self._event(owner_id, event_id, revision)
        verified = VerifiedDesign.model_validate(state.verified)
        pending_id = (state.export or {}).get("export_id") if state.stage == "exporting" else None
        async with self._canva(owner_id, "export") as canva:
            # A pending export is resumed by its persisted job ID, never requested again.
            receipt: ExportReceipt = (
                await canva.poll_png_export(event, verified, pending_id)
                if pending_id
                else await canva.request_png_export(event, verified)
            )
        export = {"export_id": receipt.export_id, "state": receipt.state}
        if receipt.state == "failed":
            # A failed job yields no file, so the next export call may request a fresh one.
            await self._save(
                owner_id,
                state,
                stage="approved",
                export=export,
                failure_code=receipt.failure_code,
            )
            raise WorkflowError("provider_failed", f"canva: {receipt.failure_code}")
        if receipt.state == "pending":
            return (await self._save(owner_id, state, stage="exporting", export=export)).public()
        async with self.client_factory() as client:
            asset = await self._prep(owner_id).store_flyer_export(
                owner_id, event_id, revision, verified, receipt, ExportDownloader(client)
            )
        state = await self._save(
            owner_id,
            state,
            stage="stored",
            export=export,
            asset=asset.preview_metadata(),
            failure_code=None,
        )
        return state.public()

    async def abandon_flyer(self, owner_id: str, event_id: str, revision: int) -> dict[str, Any]:
        """Organizer-only. Records the opt-out; invitations then no longer require a flyer."""
        async with self._lock(owner_id, event_id):

            async def run() -> dict[str, Any]:
                await require_event(self.store, owner_id, event_id)
                state = await self.flyers.get(owner_id, event_id)
                if state is None:
                    raise WorkflowError("needs_review", "no flyer has been started")
                if state.event_revision != revision:
                    raise WorkflowError("revision_conflict", "flyer is for another revision")
                state = await self._save(
                    owner_id,
                    state,
                    stage="abandoned",
                    continuation_token=None,
                    history=[*state.history, state.archived()],
                )
                return state.public()

            return await self._guard(run())


# MCP tools for Superhuman Go ----------------------------------------------------------------

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
CANVA = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
EventId = Annotated[str, Field(min_length=1, max_length=128)]
Revision = Annotated[int, Field(ge=1)]


def register_asset_tools(mcp: FastMCP, coordinator: AssetCoordinator, deps: EventToolDeps) -> None:
    async def run(action: Awaitable[Any]) -> Any:
        try:
            return await action
        except WorkflowError as error:
            raise ToolError(str(error)) from None

    @mcp.tool(annotations=READ)
    async def get_event_assets(event_id: EventId, ctx: Context) -> dict[str, Any]:
        """Status of this event's flyer/document assets: which Go asset prose is missing or
        unreviewed, the Canva flyer stage, and whether Canva/Storage are connected."""
        who = await principal(deps, ctx)
        return await run(coordinator.status(who.owner_id, event_id))

    @mcp.tool(annotations=WRITE)
    async def request_asset_prose(
        event_id: EventId, expected_revision: Revision, ctx: Context
    ) -> dict[str, Any]:
        """Queue the five asset-prose kinds (flyer_brief, flyer_copy, event_document,
        plain_language_summary, flyer_alt_text) for you to write with save_generated_content."""
        who = await principal(deps, ctx)
        return await run(coordinator.request_prose(who.owner_id, event_id, expected_revision))

    @mcp.tool(annotations=WRITE)
    async def prepare_event_document(
        event_id: EventId, expected_revision: Revision, ctx: Context
    ) -> dict[str, Any]:
        """Render your saved event_document + plain_language_summary into the private event
        document for this revision. Returns awaiting_go if either is missing."""
        who = await principal(deps, ctx)
        return await run(coordinator.prepare_document(who.owner_id, event_id, expected_revision))

    @mcp.tool(annotations=CANVA)
    async def start_canva_flyer(
        event_id: EventId, expected_revision: Revision, ctx: Context
    ) -> dict[str, Any]:
        """Create one custom Canva flyer from your saved flyer_brief and flyer_copy. Repeating
        the call for the same revision returns the existing flyer instead of a second design."""
        who = await principal(deps, ctx)
        return await run(coordinator.start_flyer(who.owner_id, event_id, expected_revision))

    @mcp.tool(annotations=CANVA)
    async def poll_canva_flyer(
        event_id: EventId, expected_revision: Revision, ctx: Context
    ) -> dict[str, Any]:
        """Check a pending Canva flyer creation after its next_poll_at time."""
        who = await principal(deps, ctx)
        return await run(coordinator.poll_flyer(who.owner_id, event_id, expected_revision))

    @mcp.tool(annotations=CANVA)
    async def preview_canva_flyer(
        event_id: EventId, expected_revision: Revision, ctx: Context
    ) -> dict[str, Any]:
        """Verify the flyer shows the exact title/time/location and produce the preview the
        organizer must approve in the website. You cannot approve it yourself."""
        who = await principal(deps, ctx)
        return await run(coordinator.preview_flyer(who.owner_id, event_id, expected_revision))

    @mcp.tool(annotations=CANVA)
    async def export_canva_flyer(
        event_id: EventId, expected_revision: Revision, ctx: Context
    ) -> dict[str, Any]:
        """Export the organizer-approved flyer as PNG into private Storage for this revision."""
        who = await principal(deps, ctx)
        return await run(coordinator.export_flyer(who.owner_id, event_id, expected_revision))


# Organizer REST routes ------------------------------------------------------------------------

STATUS = {
    "unauthenticated": 401,
    "forbidden": 403,
    "not_found": 404,
    "integration_not_connected": 503,
    "provider_failed": 502,
}


class RevisionBody(BaseModel):
    expected_revision: int = Field(ge=1)


class ApproveFlyerBody(RevisionBody):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class InclusionBody(RevisionBody):
    facts: InclusionInput


OwnerResolver = Callable[[str | None], Awaitable[str]]
PathId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


def asset_router(coordinator: AssetCoordinator, resolve_owner: OwnerResolver) -> APIRouter:
    router = APIRouter(prefix="/api/events/{event_id}/assets", tags=["assets"])

    async def respond(authorization: str | None, call: Callable[[str], Awaitable[Any]]):
        try:
            owner_id = await resolve_owner(authorization)
            body = await call(owner_id)
        except Exception as error:
            failure = _as_workflow_error(error)
            status = getattr(error, "status", None) or STATUS.get(failure.code, 409)
            message = str(failure).removeprefix(f"{failure.code}: ")
            return JSONResponse(
                {"detail": {"code": failure.code, "message": message}},
                status_code=status,
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    Auth = Annotated[str | None, Header()]

    @router.get("")
    async def status(event_id: PathId, authorization: Auth = None):
        return await respond(authorization, lambda o: coordinator.status(o, event_id))

    @router.post("/prose")
    async def prose(event_id: PathId, body: RevisionBody, authorization: Auth = None):
        return await respond(
            authorization,
            lambda o: coordinator.request_prose(o, event_id, body.expected_revision),
        )

    @router.post("/document")
    async def document(event_id: PathId, body: RevisionBody, authorization: Auth = None):
        return await respond(
            authorization,
            lambda o: coordinator.prepare_document(o, event_id, body.expected_revision),
        )

    @router.post("/inclusion")
    async def inclusion(event_id: PathId, body: InclusionBody, authorization: Auth = None):
        return await respond(
            authorization,
            lambda o: coordinator.inclusion(o, event_id, body.expected_revision, body.facts),
        )

    flyer_actions = {
        "": coordinator.start_flyer,
        "/poll": coordinator.poll_flyer,
        "/preview": coordinator.preview_flyer,
        "/export": coordinator.export_flyer,
        "/abandon": coordinator.abandon_flyer,
    }

    def flyer_route(action: Callable[[str, str, int], Awaitable[Any]]):
        async def route(event_id: PathId, body: RevisionBody, authorization: Auth = None):
            return await respond(
                authorization, lambda o: action(o, event_id, body.expected_revision)
            )

        return route

    for suffix, action in flyer_actions.items():
        router.add_api_route(f"/flyer{suffix}", flyer_route(action), methods=["POST"])

    @router.post("/flyer/approve")
    async def approve(event_id: PathId, body: ApproveFlyerBody, authorization: Auth = None):
        return await respond(
            authorization,
            lambda o: coordinator.approve_flyer(
                o, event_id, body.expected_revision, body.preview_digest
            ),
        )

    return router


def _include_before_mounts(app: FastAPI, router: APIRouter) -> None:
    """Include routes ahead of any catch-all Mount (the MCP app is mounted at "/")."""
    before = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[before:]
    del app.router.routes[before:]
    index = next(
        (i for i, route in enumerate(app.router.routes) if isinstance(route, Mount)),
        len(app.router.routes),
    )
    app.router.routes[index:index] = added


# Composition -------------------------------------------------------------------------------


def register_assets(
    app: FastAPI,
    mcp: FastMCP,
    events: EventToolDeps,
    coordinator: AssetCoordinator,
    resolve_owner: OwnerResolver,
    *,
    attachments: Any | None = None,
) -> None:
    """Testable core: tools, routes and the Distributor's required-attachment preflight."""
    if events.distributor is not None and attachments is not None:
        events.distributor.attachments = attachments
        events.distributor.attachment_policy = FlyerRequiredPolicy(coordinator.flyers)
    register_asset_tools(mcp, coordinator, events)
    _include_before_mounts(app, asset_router(coordinator, resolve_owner))


def register_asset_services(
    app: FastAPI, mcp: FastMCP, settings: Settings, events: EventToolDeps
) -> None:
    """Supabase-mode composition, called from main.py. Never fakes a provider connection."""
    from hackathon_backend.auth.identity import authenticate
    from hackathon_backend.providers.canva.oauth import CanvaTokens
    from hackathon_backend.repositories.assets import SupabaseAssetStorage
    from hackathon_backend.repositories.transport import Database
    from hackathon_backend.workflows.canva_connect import (
        canva_connect_configured,
        canva_connect_router,
        canva_oauth_config,
    )

    database = Database(settings, admin=True)
    vault = None
    if settings.credential_encryption_key:
        from hackathon_backend.repositories.vault import SupabaseCredentialVault

        vault = SupabaseCredentialVault(database, settings.credential_encryption_key)
    flyers: FlyerStateStore = (
        SupabaseFlyerStateStore(
            database, settings.credential_encryption_key, legacy=VaultFlyerStateStore(vault)
        )
        if vault
        else MemoryFlyerStateStore()
    )

    def storage_for(owner_id: str) -> SupabaseAssetStorage:
        return SupabaseAssetStorage(database, owner_id)

    tokens = CanvaTokens(vault, canva_oauth_config(settings)) if vault else None
    if canva_connect_configured(settings):
        _include_before_mounts(app, canva_connect_router(settings, tokens))
    coordinator = AssetCoordinator(
        events.store,
        storage_for=storage_for,
        canva=VaultCanvaSessions(vault, tokens=tokens)
        if vault
        else None,
        flyers=flyers,
        holidays=HolidayCalendar(),
    )

    async def resolve_owner(authorization: str | None) -> str:
        return (await authenticate(settings, authorization)).owner_id

    register_assets(
        app,
        mcp,
        events,
        coordinator,
        resolve_owner,
        attachments=OwnerScopedAttachments(storage_for, settings.supabase_url),
    )
