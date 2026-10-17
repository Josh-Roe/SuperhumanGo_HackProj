"""WORKFLOW_DEV_MODE: in-memory store, one seeded organizer, and dev-only REST controls.

This exists to prove the live Go -> event tool -> saved content loop and the Google publish/update
path before Member 2's Supabase repositories and Member 1's screens land. State is lost on
restart and is not Supabase evidence. Every route requires the dev organizer's connector token.
"""

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.providers.google.calendar import GoogleCalendarAPI
from hackathon_backend.providers.google.gmail import GoogleGmailAPI
from hackathon_backend.providers.google.oauth import (
    GoogleOAuthConfig,
    VaultTokenSource,
    authorization_url,
    exchange_code,
    id_token_claims,
)
from hackathon_backend.workflows import go_work
from hackathon_backend.workflows.distribution import Distributor
from hackathon_backend.workflows.go_work import WorkflowError
from hackathon_backend.workflows.memory import InMemoryPrincipalResolver, InMemoryWorkflowStore
from hackathon_backend.workflows.models import Approval, EventSnapshot, Invitee, new_id, utcnow
from hackathon_backend.workflows.rsvp import RSVPTracker

DEV_OWNER = "dev-organizer"


class MemoryVault:
    """Dev-only CredentialVault. Member 2 replaces it with encrypted server-side storage."""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, str]] = {}

    async def get_refresh_token(self, owner_id: str) -> str | None:
        return self._tokens.get(owner_id, (None, None))[0]

    async def put_refresh_token(self, owner_id, account_email, refresh_token, scopes) -> None:
        self._tokens[owner_id] = (refresh_token, account_email)

    async def get_account_email(self, owner_id: str) -> str | None:
        return self._tokens.get(owner_id, (None, None))[1]


@dataclass
class DevWorkflow:
    deps: EventToolDeps
    store: InMemoryWorkflowStore
    connector_token: str
    oauth: GoogleOAuthConfig | None
    vault: MemoryVault
    tokens: VaultTokenSource | None = None  # forgotten on reconnect so new grants apply at once


def seed_event(invitees: list[str]) -> EventSnapshot:
    start = (utcnow() + timedelta(days=7)).replace(hour=1, minute=0, second=0, microsecond=0)
    return EventSnapshot(
        id="dev-event-1",
        owner_id=DEV_OWNER,
        revision=1,
        title="Community Picnic (test event)",
        description="A test event for verifying the Go integration. Venue facts are unverified.",
        location="Dolores Park, San Francisco, CA",
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        timezone="America/Los_Angeles",
        links=[],
        organizer_contact=os.getenv("DEV_ORGANIZER_CONTACT", "organizer@example.com"),
        invitees=[
            Invitee(id=f"dev-invitee-{n}", email=email) for n, email in enumerate(invitees, 1)
        ],
    )


def dev_workflow_from_env() -> DevWorkflow | None:
    if os.getenv("WORKFLOW_DEV_MODE", "").strip() != "1":
        return None
    token = os.getenv("DEV_CONNECTOR_TOKEN", "").strip()
    if len(token) < 24:
        raise ValueError("WORKFLOW_DEV_MODE requires DEV_CONNECTOR_TOKEN (24+ characters)")
    store = InMemoryWorkflowStore()
    invitees = [e.strip() for e in os.getenv("DEV_INVITEES", "").split(",") if e.strip()]
    store.put_event(seed_event(invitees))
    principals = InMemoryPrincipalResolver()
    principals.register(token, DEV_OWNER)
    oauth = GoogleOAuthConfig.from_env()
    vault = MemoryVault()
    deps = EventToolDeps(store=store, principals=principals)
    tokens = None
    if oauth is not None:
        tokens = VaultTokenSource(oauth, vault)
        calendar, gmail = GoogleCalendarAPI(tokens), GoogleGmailAPI(tokens)
        deps.distributor = Distributor(store, calendar, gmail, tokens)
        deps.rsvp = RSVPTracker(store, calendar, gmail, tokens)
    return DevWorkflow(deps, store, token, oauth, vault, tokens)


class Revise(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    title: str | None = None


class Approve(BaseModel):
    content_id: str
    action: str = "publish"  # publish | update | draft_only


def dev_router(dev: DevWorkflow) -> APIRouter:
    router = APIRouter(prefix="/api/dev", tags=["dev-only"])
    states: dict[str, str] = {}

    def organizer(request: Request) -> str:
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            credential.encode(), dev.connector_token.encode()
        ):
            raise HTTPException(401, "unauthenticated", headers={"WWW-Authenticate": "Bearer"})
        return DEV_OWNER

    def fail(error: WorkflowError) -> HTTPException:
        status = {"forbidden": 404, "revision_conflict": 409}.get(error.code, 400)
        return HTTPException(status, str(error))

    @router.get("/events/{event_id}")
    async def status(event_id: str, owner: str = Depends(organizer)):
        try:
            event = await go_work.require_event(dev.store, owner, event_id)
        except WorkflowError as error:
            raise fail(error) from None
        rsvps = await dev.deps.rsvp.summary(owner, event_id) if dev.deps.rsvp else []
        return {
            "label": "dev mode: in-memory, not Supabase",
            "event": event.model_dump(mode="json"),
            "work": [w.model_dump(mode="json") for w in dev.store.work.values()],
            "content": [
                c.model_dump(mode="json")
                for c in dev.store.content.values()
                if c.event_id == event_id
            ],
            "operations": [
                o.model_dump(mode="json") for o in await dev.store.list_operations(owner, event_id)
            ],
            "calendar": (
                b.model_dump(mode="json") if (b := dev.store.calendar.get(event_id)) else None
            ),
            "gmail": (g.model_dump(mode="json") if (g := dev.store.gmail.get(event_id)) else None),
            "rsvps": [r.model_dump(mode="json") for r in rsvps],
            "google_connected": await dev.vault.get_account_email(owner) is not None,
        }

    @router.post("/events/{event_id}/prepare")
    async def prepare(event_id: str, owner: str = Depends(organizer)):
        try:
            item = await go_work.enqueue_preparation(dev.store, owner, event_id)
        except WorkflowError as error:
            raise fail(error) from None
        return item.model_dump(mode="json")

    @router.post("/events/{event_id}/revise")
    async def revise(event_id: str, change: Revise, owner: str = Depends(organizer)):
        try:
            event = await go_work.require_event(dev.store, owner, event_id)
        except WorkflowError as error:
            raise fail(error) from None
        updates = change.model_dump(exclude_none=True)
        revised = EventSnapshot.model_validate(
            {**event.model_dump(), **updates, "revision": event.revision + 1}
        )
        dev.store.put_event(revised)
        item = await go_work.enqueue_preparation(dev.store, owner, event_id)
        return {"revision": revised.revision, "work_id": item.id}

    @router.post("/events/{event_id}/approve")
    async def approve(event_id: str, body: Approve, owner: str = Depends(organizer)):
        content = await dev.store.get_content(owner, body.content_id)
        event = await dev.store.get_event(owner, event_id)
        if content is None or event is None or content.event_id != event_id:
            raise HTTPException(404, "forbidden: content not found for this event")
        dev.store.content[content.id] = content.model_copy(update={"state": "ready"})
        approval = Approval(
            id=new_id(),
            event_id=event_id,
            event_revision=event.revision,
            action=body.action,
            invitation_content_id=content.id,
        )
        dev.store.put_approval(approval)
        return approval.model_dump(mode="json")

    @router.post("/events/{event_id}/content/{content_id}/ready")
    async def mark_ready(event_id: str, content_id: str, owner: str = Depends(organizer)):
        content = await dev.store.get_content(owner, content_id)
        if content is None or content.event_id != event_id:
            raise HTTPException(404, "forbidden: content not found for this event")
        dev.store.content[content.id] = content.model_copy(update={"state": "ready"})
        return {"id": content_id, "state": "ready"}

    @router.post("/google/connect")
    async def connect(owner: str = Depends(organizer)):
        if dev.oauth is None:
            raise HTTPException(400, "integration_not_connected: set GOOGLE_CLIENT_ID/SECRET/URI")
        state = secrets.token_urlsafe(24)
        states[state] = owner
        return {"authorization_url": authorization_url(dev.oauth, state)}

    @router.get("/google/callback")
    async def callback(state: str = "", code: str = "", error: str = ""):
        owner = states.pop(state, None)
        if owner is None or dev.oauth is None:
            raise HTTPException(400, "invalid or expired OAuth state")
        if error or not code:
            raise HTTPException(400, "Google authorization was not granted")
        grant = await exchange_code(dev.oauth, code)
        if not grant.refresh_token:
            raise HTTPException(400, "Google returned no refresh token; revoke access and retry")
        email = id_token_claims(grant.id_token or "").get("email", "")
        await dev.vault.put_refresh_token(owner, email, grant.refresh_token, grant.scope)
        if dev.tokens is not None:
            dev.tokens.forget(owner)
        return {"connected": True, "account": email}

    return router
