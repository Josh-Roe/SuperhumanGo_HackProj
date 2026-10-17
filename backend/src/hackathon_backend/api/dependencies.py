"""Composition factories supplied to Member 3; this module registers no routes/tools."""

from hackathon_backend.auth.connectors import SupabasePrincipalResolver
from hackathon_backend.config import Settings
from hackathon_backend.mcp_tools.event_tools import EventToolDeps
from hackathon_backend.providers.google import GoogleCalendarAPI, GoogleGmailAPI
from hackathon_backend.providers.google.oauth import GoogleOAuthConfig, VaultTokenSource
from hackathon_backend.repositories.assets import SupabaseAttachmentSource
from hackathon_backend.repositories.organizer import OrganizerRepository
from hackathon_backend.repositories.transport import Database
from hackathon_backend.repositories.vault import SupabaseCredentialVault
from hackathon_backend.repositories.workflow import SupabaseWorkflowStore
from hackathon_backend.workflows.distribution import Distributor
from hackathon_backend.workflows.models import Principal
from hackathon_backend.workflows.rsvp import RSVPTracker


def create_tool_dependencies(settings: Settings) -> EventToolDeps:
    """Fail closed without server credentials. Configured does not imply live verified."""
    database = Database(settings, admin=True)
    store = SupabaseWorkflowStore(database)
    deps = EventToolDeps(store=store, principals=SupabasePrincipalResolver(database))
    if all(
        (
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_redirect_uri,
            settings.credential_encryption_key,
        )
    ):
        vault = SupabaseCredentialVault(database, settings.credential_encryption_key)
        tokens = VaultTokenSource(
            GoogleOAuthConfig(
                settings.google_client_id,
                settings.google_client_secret,
                settings.google_redirect_uri,
            ),
            vault,
        )
        calendar, gmail = GoogleCalendarAPI(tokens), GoogleGmailAPI(tokens)
        deps.distributor = Distributor(
            store, calendar, gmail, tokens, SupabaseAttachmentSource(database)
        )
        deps.rsvp = RSVPTracker(store, calendar, gmail, tokens)
    return deps


def task_repository(settings: Settings, principal: Principal) -> OrganizerRepository:
    """Only call after resolving the connector token; owner_id is never a tool argument."""
    return OrganizerRepository(Database(settings, admin=True), principal.owner_id)
