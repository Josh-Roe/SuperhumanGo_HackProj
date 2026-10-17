"""Disposable-organizer REST/MCP rehearsal; never generates prose or sends invitations.

Run with backend's Python and --fixture pointing to a mode-0600 JSON file containing
two pre-provisioned users: {users: [{id, email, password, connector}, ...]}.
Only example.invalid accounts are accepted. Provisioning and removal are separate
admin actions; the fixture journal records event IDs even if a later check fails.
"""

import argparse
import asyncio
import json
import stat
import time
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def unpack(result):
    if result.isError:
        raise AssertionError("MCP tool failed; inspect sanitized server logs")
    value = result.structuredContent
    if value is None:
        value = json.loads(
            next(item.text for item in result.content if item.type == "text")
        )
    return (
        value["result"]
        if isinstance(value, dict) and set(value) == {"result"}
        else value
    )


async def check(base, fixture_path):
    if stat.S_IMODE(fixture_path.stat().st_mode) != 0o600:
        raise ValueError("Fixture credentials must have mode 0600")
    fixture = json.loads(fixture_path.read_text())
    users = fixture["users"]
    if len(users) != 2 or any(
        not u["email"].endswith("@example.invalid") for u in users
    ):
        raise ValueError("Use exactly two disposable example.invalid organizers")
    report = {"checks": [], "timings_seconds": {}}
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as http:
        config = (await http.get(base + "/api/config")).json()
        for user in users:
            response = await http.post(
                config["supabase_url"] + "/auth/v1/token?grant_type=password",
                headers={"apikey": config["supabase_publishable_key"]},
                json={"email": user["email"], "password": user["password"]},
            )
            assert response.status_code == 200, "Synthetic Auth sign-in failed"
            user["session"] = response.json()["access_token"]

        first, second = users

        async def rest(method, path, expected=200, *, user=first, **kwargs):
            start = time.monotonic()
            response = await http.request(
                method,
                base + path,
                headers={"Authorization": "Bearer " + user["session"]},
                **kwargs,
            )
            report["timings_seconds"][method + " " + path.rsplit("/", 1)[-1]] = round(
                time.monotonic() - start, 3
            )
            assert response.status_code == expected, (
                f"{method} {path}: expected {expected}, got {response.status_code}"
            )
            return response.json() if response.content else None

        async with (
            httpx.AsyncClient(
                headers={"Authorization": "Bearer " + first["connector"]}, timeout=60
            ) as client,
            streamable_http_client(base + "/mcp", http_client=client) as (
                read,
                write,
                _,
            ),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            args = {
                "idempotency_key": "live-backend-" + uuid4().hex,
                "title": "Disposable backend rehearsal",
                "description": "Synthetic fixture; no provider writes or Go prose claimed.",
                "location": "Synthetic room A",
                "starts_at": "2026-11-03T18:00:00-08:00",
                "ends_at": "2026-11-03T19:00:00-08:00",
                "timezone": "America/Los_Angeles",
                "invitees": [],
            }
            event = unpack(await session.call_tool("create_event", args))
            fixture["event_id"] = event["id"]
            # Do not persist short-lived Auth access tokens to the journal.
            fixture_path.write_text(
                json.dumps(
                    {
                        **fixture,
                        "users": [
                            {k: v for k, v in u.items() if k != "session"}
                            for u in users
                        ],
                    }
                )
            )
            again = unpack(await session.call_tool("create_event", args))
            assert (again["id"], again["revision"]) == (event["id"], 1)
            rows = unpack(await session.call_tool("list_events"))
            assert any(row["id"] == event["id"] for row in rows)
            changed = unpack(
                await session.call_tool(
                    "update_event",
                    {
                        "event_id": event["id"],
                        "expected_revision": 1,
                        "location": "Synthetic room B",
                    },
                )
            )
            assert changed["id"] == event["id"] and changed["revision"] == 2
            stale = await session.call_tool(
                "update_event",
                {
                    "event_id": event["id"],
                    "expected_revision": 1,
                    "location": "Stale synthetic room",
                },
            )
            assert stale.isError and "revision_conflict" in str(stale)
        path = "/api/events/" + event["id"]
        saved = await rest("GET", path)
        assert saved["revision"] == 2 and saved["location"] == "Synthetic room B"
        assert any(row["id"] == event["id"] for row in await rest("GET", "/api/events"))
        report["checks"].append(
            "MCP/REST shared identity, idempotency and revision conflict"
        )
        await rest("GET", path, 404, user=second)
        await rest(
            "PUT",
            path,
            404,
            user=second,
            json={
                **{
                    k: saved[k]
                    for k in args
                    if k not in {"idempotency_key", "invitees"}
                },
                "invitees": [],
                "expected_revision": 2,
            },
        )
        assert all(
            row["id"] != event["id"]
            for row in await rest("GET", "/api/events", user=second)
        )
        report["checks"].append("cross-organizer REST reads and writes denied")
        await rest("PUT", path, 422, json={"expected_revision": 2})
        facts = {"expected_version": 0, "facts": {"traditions": []}}
        inclusion = await rest("PUT", path + "/inclusion", json=facts)
        assert inclusion["version"] == 1 and inclusion["saved_at_event_revision"] == 2
        await rest("PUT", path + "/inclusion", 409, json=facts)
        await rest("GET", path + "/inclusion", 404, user=second)
        loaded = await rest("GET", path + "/inclusion")
        assert loaded["version"] == 1 and loaded["facts"]["traditions"] == []
        report["checks"].append("inclusion version CAS, persistence and privacy")
        work = await rest("POST", path + "/prepare", 202, json={"expected_revision": 2})
        retry = await rest(
            "POST", path + "/prepare", 202, json={"expected_revision": 2}
        )
        assert retry["id"] == work["id"]
        for endpoint in (
            "workspace",
            "work",
            "bindings",
            "approvals",
            "operations",
            "rsvps",
            "artifacts",
            "progress",
        ):
            await rest("GET", path + "/" + endpoint)
            await rest("GET", path + "/" + endpoint, 404, user=second)
        report["checks"].append("preparation retry identity and private read contracts")
        report["event_id"] = event["id"]
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", default="https://superhuman-go-event-backend.onrender.com"
    )
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    if not args.base.startswith("https://"):
        parser.error("Use a trusted HTTPS backend")
    asyncio.run(check(args.base.rstrip("/"), args.fixture))
