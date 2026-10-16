"""Synthetic fixtures only: they do not claim a live Go generation or Canva write."""

import base64
from datetime import UTC, datetime

from hackathon_backend.services.assets.models import EventSnapshot, GoContent

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
)


def event(revision=1, **changes):
    return EventSnapshot(
        **{
            "id": "fixture-event",
            "owner_id": "fixture-owner",
            "revision": revision,
            "title": "Synthetic integration fixture",
            "location": "Fixture Room A",
            "starts_at": "2026-10-16T18:00:00-07:00",
            "ends_at": "2026-10-16T19:00:00-07:00",
            "timezone": "America/Los_Angeles",
            **changes,
        }
    )


def go(snapshot, kind="flyer_brief", **changes):
    return GoContent(
        **{
            "event_id": snapshot.id,
            "owner_id": snapshot.owner_id,
            "event_revision": snapshot.revision,
            "producer": "superhuman_go",
            "generation_id": "synthetic-test-fixture",
            "kind": kind,
            "body": "SYNTHETIC TEST DATA. No live Go generation is represented.",
            **changes,
        }
    )
