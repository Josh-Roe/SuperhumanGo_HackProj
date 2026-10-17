import asyncio
from datetime import timedelta

import pytest
from pydantic import ValidationError
from test_assets_support import NOW, event, go

from hackathon_backend.providers.canva import CanvaError, CanvaMCPAdapter, ElementMapping
from hackathon_backend.services.assets.models import Approval, DesignRef, StaleRevisionError


class Session:
    def __init__(self, responses):
        self.responses = {name: list(items) for name, items in responses.items()}
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.responses[name].pop(0)


def design(snapshot=None):
    snapshot = snapshot or event()
    return DesignRef(
        owner_id=snapshot.owner_id,
        event_id=snapshot.id,
        event_revision=snapshot.revision,
        generation_id="synthetic-test-fixture",
        design_id="D-synthetic",
        edit_url="https://www.canva.com/design/fixture/edit",
        view_url="https://www.canva.com/design/fixture/view",
    )


def pending(token="private-poll-token", wait=15):
    return {
        "status": "pending",
        "job_id": "test-job",
        "continuation_token": token,
        "polling_policy": {"wait_seconds": wait},
    }


def test_custom_creation_uses_go_brief_and_no_template():
    session = Session({"create-design": [pending()]})
    adapter = CanvaMCPAdapter(session, owner_id="fixture-owner")
    job = asyncio.run(adapter.create_flyer(event(), go(event()), now=NOW))
    assert job.state == "pending" and job.next_poll_at == NOW + timedelta(seconds=15)
    name, args = session.calls[0]
    assert name == "create-design" and "brand_template_id" not in args
    assert go(event()).body in args["brief"] and event().location in args["brief"]
    assert args["format"] == "Flyer (Portrait A4)"
    assert "private-poll-token" not in job.model_dump_json() + repr(job)


def test_poll_policy_new_token_and_completion():
    completed = {
        "status": "completed",
        "job_id": "test-job",
        "design": {"id": "D-synthetic", "edit_url": design().edit_url, "url": design().view_url},
    }
    session = Session(
        {
            "create-design": [pending()],
            "get-create-design-async-job": [pending("new-token", 30), completed],
        }
    )
    adapter = CanvaMCPAdapter(session, owner_id="fixture-owner")
    first = asyncio.run(adapter.create_flyer(event(), go(event()), now=NOW))
    with pytest.raises(ValueError, match="window"):
        asyncio.run(adapter.poll_creation(event(), first, now=NOW))
    assert len(session.calls) == 1
    second = asyncio.run(adapter.poll_creation(event(), first, now=NOW + timedelta(seconds=15)))
    last = asyncio.run(adapter.poll_creation(event(), second, now=NOW + timedelta(seconds=45)))
    assert last.state == "completed" and last.design.design_id == "D-synthetic"
    assert session.calls[-1][1]["continuation_token"] == "new-token"
    with pytest.raises(StaleRevisionError):
        asyncio.run(adapter.poll_creation(event(2), second, now=NOW + timedelta(seconds=50)))


def test_creation_shortlink_is_normalized_by_design_id_without_following_redirects():
    session = Session(
        {
            "create-design": [pending()],
            "get-create-design-async-job": [
                {
                    "status": "completed",
                    "job_id": "test-job",
                    "design": {
                        "id": "D-synthetic",
                        "url": "https://canva.link/synthetic",
                        "edit_url": "https://canva.link/synthetic",
                    },
                }
            ],
            "get-design": [
                {
                    "design": {
                        "id": "D-synthetic",
                        "urls": {"edit_url": design().edit_url, "view_url": design().view_url},
                    }
                }
            ],
        }
    )
    adapter = CanvaMCPAdapter(session, owner_id="fixture-owner")
    job = asyncio.run(adapter.create_flyer(event(), go(event()), now=NOW))
    done = asyncio.run(adapter.poll_creation(event(), job, now=NOW + timedelta(seconds=15)))
    assert done.design.edit_url == design().edit_url and done.design.view_url == design().view_url
    assert session.calls[-1][0] == "get-design"
    assert session.calls[-1][1]["design_id"] == "D-synthetic"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/design",
        "https://canva.link.evil.example/a",
        "https://user:secret@canva.link/a",
        "http://canva.link/a",
        "https://www.canva.com:8443/a",
    ],
)
def test_untrusted_completion_link_does_not_trigger_lookup_or_http_redirect(url):
    session = Session(
        {"create-design": [{"status": "completed", "design": {"id": "D-synthetic", "url": url}}]}
    )
    with pytest.raises(CanvaError, match="design_url"):
        asyncio.run(
            CanvaMCPAdapter(session, owner_id="fixture-owner").create_flyer(event(), go(event()))
        )
    assert len(session.calls) == 1


def test_shortlink_metadata_must_belong_to_created_design():
    session = Session(
        {
            "create-design": [
                {
                    "status": "completed",
                    "design": {"id": "D-synthetic", "url": "https://canva.link/synthetic"},
                }
            ],
            "get-design": [
                {
                    "design": {
                        "id": "another-design",
                        "urls": {"edit_url": design().edit_url, "view_url": design().view_url},
                    }
                }
            ],
        }
    )
    with pytest.raises(CanvaError, match="identity_mismatch"):
        asyncio.run(
            CanvaMCPAdapter(session, owner_id="fixture-owner").create_flyer(event(), go(event()))
        )


def test_quota_failure_is_returned_without_retry():
    session = Session(
        {
            "create-design": [
                {
                    "status": "failed",
                    "failure": {"code": "quota_exceeded", "message": "private upstream details"},
                }
            ]
        }
    )
    result = asyncio.run(
        CanvaMCPAdapter(session, owner_id="fixture-owner").create_flyer(
            event(), go(event()), now=NOW
        )
    )
    assert result.failure_code == "quota_exceeded" and result.state == "failed"
    assert len(session.calls) == 1 and "private upstream" not in result.model_dump_json()


def test_non_go_wrong_kind_and_other_owner_never_reach_canva():
    with pytest.raises(ValidationError):
        go(event(), producer="organizer")
    session = Session({})
    adapter = CanvaMCPAdapter(session, owner_id="another-owner")
    with pytest.raises(PermissionError):
        asyncio.run(adapter.create_flyer(event(), go(event())))
    with pytest.raises(ValueError, match="flyer brief"):
        asyncio.run(
            CanvaMCPAdapter(session, owner_id="fixture-owner").create_flyer(
                event(), go(event(), "event_document")
            )
        )
    assert session.calls == []


def editing_fixture(extra_text=""):
    old, new = (
        event(),
        event(
            2,
            location="Fixture Room B",
            starts_at="2026-10-16T19:00:00-07:00",
            ends_at="2026-10-16T20:00:00-07:00",
        ),
    )
    mappings = tuple(
        ElementMapping(role=role, element_id=role, previous_text=text)
        for role, text in old.flyer_fields().items()
    )
    opened = {
        "transaction": {"transaction_id": "txn-fixture"},
        "richtexts": [
            {
                "element_id": m.element_id,
                "page_index": 1,
                "regions": [{"type": "character", "text": m.previous_text}],
            }
            for m in mappings
        ],
    }
    session = Session(
        {
            "start-editing-transaction": [opened],
            "perform-editing-operations": [
                {
                    "thumbnails": [
                        {"url": "https://design-manipulation-download.canva.com/preview"}
                    ],
                    "edit_operation_results": [
                        {
                            "status": "success",
                            "operation_info": {
                                "type": "replace_text",
                                "element_id": mapping.element_id,
                            },
                        }
                        for mapping in mappings
                    ],
                }
            ],
            "commit-editing-transaction": [{"status": "committed"}],
            "get-design-content": [
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "\n".join(new.flyer_fields().values()) + extra_text,
                        }
                    ]
                }
            ],
            "cancel-editing-transaction": [{}],
            "export-design": [
                {
                    "job": {
                        "status": "success",
                        "id": "export-fixture",
                        "urls": ["https://export-download.canva.com/fixture.png"],
                    }
                }
            ],
        }
    )
    adapter = CanvaMCPAdapter(session, owner_id=old.owner_id)
    preview = asyncio.run(
        adapter.stage_update(new, design(old), go(new, "flyer_copy"), mappings, now=NOW)
    )
    approval = Approval(
        owner_id=new.owner_id,
        event_id=new.id,
        event_revision=new.revision,
        preview_digest=preview.digest,
        approved_at=NOW + timedelta(seconds=1),
        approval_id="fixture-approval",
    )
    return adapter, session, new, preview, approval


def test_transaction_preview_exact_approval_readback_and_export():
    adapter, session, new, preview, approval = editing_fixture()
    assert not any(name == "commit-editing-transaction" for name, _ in session.calls)
    with pytest.raises(PermissionError):
        asyncio.run(
            adapter.commit_update(
                new, preview, approval.model_copy(update={"preview_digest": "0" * 64})
            )
        )
    result = asyncio.run(adapter.commit_update(new, preview, approval))
    assert result.state == "verified" and result.organizer_reviewed
    assert result.design.event_revision == 2 and result.design.design_id == "D-synthetic"
    assert asyncio.run(adapter.export_png(new, result))["export_id"] == "export-fixture"


def test_preview_tampering_and_newer_event_rejected_before_commit():
    adapter, session, new, preview, approval = editing_fixture()
    altered = preview.model_copy(update={"expected": {**preview.expected, "location": "Wrong"}})
    with pytest.raises(PermissionError):
        asyncio.run(adapter.commit_update(new, altered, approval))
    with pytest.raises(PermissionError):
        asyncio.run(
            adapter.commit_update(
                new,
                preview.model_copy(
                    update={"thumbnail_urls": ("https://media.canva.com/another-preview",)}
                ),
                approval,
            )
        )
    with pytest.raises(StaleRevisionError):
        asyncio.run(adapter.commit_update(event(3), preview, approval))
    assert not any(name == "commit-editing-transaction" for name, _ in session.calls)


def test_old_copy_remaining_needs_review_and_cannot_export():
    adapter, _, new, preview, approval = editing_fixture("\nFixture Room A")
    result = asyncio.run(adapter.commit_update(new, preview, approval))
    assert result.state == "needs_review" and result.stale_roles == ("location",)
    assert not result.organizer_reviewed
    with pytest.raises(StaleRevisionError):
        asyncio.run(adapter.export_png(new, result))


def test_changed_element_mapping_cancels_transaction():
    session = Session(
        {
            "start-editing-transaction": [
                {"transaction": {"transaction_id": "txn-fixture"}, "richtexts": []}
            ],
            "cancel-editing-transaction": [{}],
        }
    )
    mappings = tuple(
        ElementMapping(role=role, element_id=role, previous_text=text)
        for role, text in event().flyer_fields().items()
    )
    with pytest.raises(CanvaError, match="mapping_changed"):
        asyncio.run(
            CanvaMCPAdapter(session, owner_id="fixture-owner").stage_update(
                event(2), design(), go(event(2), "flyer_copy"), mappings
            )
        )
    assert session.calls[-1][0] == "cancel-editing-transaction"


def test_verification_rejects_partial_checks_and_safe_tool_errors():
    session = Session(
        {
            "get-design-content": [
                {"isError": True, "content": [{"text": "secret upstream payload"}]}
            ]
        }
    )
    adapter = CanvaMCPAdapter(session, owner_id="fixture-owner")
    with pytest.raises(ValueError, match="canonical"):
        asyncio.run(adapter.verify_text(event(), design(), {"title": event().title}))
    with pytest.raises(CanvaError, match="canva_tool_failed") as error:
        asyncio.run(adapter.verify_text(event(), design(), event().flyer_fields()))
    assert "secret" not in str(error.value)


def test_partial_edit_operation_failure_is_cancelled_without_preview_or_commit():
    session = Session(
        {
            "start-editing-transaction": [
                {
                    "transaction": {"transaction_id": "txn"},
                    "richtexts": [
                        {"element_id": role, "page_index": 1, "regions": [{"text": text}]}
                        for role, text in event().flyer_fields().items()
                    ],
                }
            ],
            "perform-editing-operations": [{"edit_operation_results": [{"status": "failed"}]}],
            "cancel-editing-transaction": [{}],
        }
    )
    mappings = tuple(
        ElementMapping(role=role, element_id=role, previous_text=text)
        for role, text in event().flyer_fields().items()
    )
    with pytest.raises(CanvaError, match="operation_failed"):
        asyncio.run(
            CanvaMCPAdapter(session, owner_id="fixture-owner").stage_update(
                event(2), design(), go(event(2), "flyer_copy"), mappings
            )
        )
    assert session.calls[-1][0] == "cancel-editing-transaction"


def test_update_preview_public_metadata_excludes_transaction_handle():
    adapter, session, new, preview, _ = editing_fixture()
    public = preview.preview_metadata()
    assert "transaction_id" not in public and public["event_revision"] == 2
    asyncio.run(adapter.cancel_update(event(3), preview))
    assert session.calls[-1][0] == "cancel-editing-transaction"


def review_fixture(*, changed_version=False):
    metadata = {
        "design": {
            "id": "D-synthetic",
            "updated_at": 100,
            "page_count": 1,
            "thumbnail": {"url": "https://media.canva.com/synthetic-preview"},
        }
    }
    newer = {"design": {**metadata["design"], "updated_at": 101}} if changed_version else metadata
    session = Session(
        {
            "get-design": [metadata, newer],
            "get-design-content": [{"text": "\n".join(event().flyer_fields().values())}] * 2,
        }
    )
    adapter = CanvaMCPAdapter(session, owner_id="fixture-owner")
    preview = asyncio.run(adapter.preview_flyer(event(), design(), now=NOW))
    approval = Approval(
        owner_id="fixture-owner",
        event_id=event().id,
        event_revision=1,
        preview_digest=preview.digest,
        approved_at=NOW,
        approval_id="synthetic-approval",
    )
    return adapter, session, preview, approval


def test_initial_flyer_requires_exact_organizer_review_and_readback():
    adapter, session, preview, approval = review_fixture()
    assert preview.preview_metadata()["thumbnail_urls"] == preview.thumbnail_urls
    assert asyncio.run(adapter.approve_flyer(event(), preview, approval)).organizer_reviewed
    assert all(
        name not in {"commit-editing-transaction", "create-design"} for name, _ in session.calls
    )


def test_manual_edit_after_preview_requires_new_review():
    adapter, _, preview, approval = review_fixture(changed_version=True)
    with pytest.raises(CanvaError, match="changed_since_preview"):
        asyncio.run(adapter.approve_flyer(event(), preview, approval))


def test_changed_review_preview_or_event_revision_cannot_be_approved():
    adapter, session, preview, approval = review_fixture()
    with pytest.raises(PermissionError):
        asyncio.run(
            adapter.approve_flyer(
                event(),
                preview.model_copy(update={"thumbnail_urls": ("https://example.com/unrelated",)}),
                approval,
            )
        )
    with pytest.raises(StaleRevisionError):
        asyncio.run(adapter.approve_flyer(event(2), preview, approval))
    assert len(session.calls) == 2


@pytest.mark.parametrize(
    "status,state", [("in_progress", "pending"), ("failed", "failed"), ("success", "completed")]
)
def test_export_receipts_preserve_job_id_without_serializing_signed_download_url(status, state):
    from hackathon_backend.providers.canva import VerifiedDesign

    session = Session(
        {
            "export-design": [
                {
                    "job": {
                        "id": "export-synthetic",
                        "status": status,
                        "urls": [
                            "https://export-download.canva.com/synthetic.png?signature=private"
                        ],
                    }
                }
            ]
        }
    )
    receipt = asyncio.run(
        CanvaMCPAdapter(session, owner_id="fixture-owner").request_png_export(
            event(), VerifiedDesign(design=design(), state="verified", missing_roles=())
        )
    )
    assert receipt.state == state and receipt.export_id == "export-synthetic"
    assert "signature" not in receipt.model_dump_json() + repr(receipt)
