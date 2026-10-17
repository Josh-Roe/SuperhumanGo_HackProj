import base64
from email import message_from_bytes
from email.policy import default

import pytest

from hackathon_backend.providers.google.mime import (
    build_message,
    is_forwarded,
    message_header,
    message_text,
    sender_email,
    strip_quoted,
)


def b64(text: str, padding: bool = False) -> str:
    encoded = base64.urlsafe_b64encode(text.encode()).decode()
    return encoded if padding else encoded.rstrip("=")


def test_build_message_round_trip_with_bcc_and_attachment():
    raw = build_message(
        sender="Organizer <org@example.com>",
        to=["org@example.com"],
        bcc=["a@example.com", "b@example.org"],
        subject="You're invited: Picnic",
        text_body="Join us at the park.",
        attachments=[("flyer.pdf", "application/pdf", b"%PDF-1.4 data")],
        headers={"In-Reply-To": "<abc@mail>", "References": "<abc@mail>"},
    )
    assert b"\r\nBcc: a@example.com, b@example.org\r\n" in raw
    parsed = message_from_bytes(raw, policy=default)
    assert parsed["Subject"] == "You're invited: Picnic"
    assert parsed["In-Reply-To"] == "<abc@mail>"
    assert parsed.get_body(("plain",)).get_content().strip() == "Join us at the park."
    attachments = list(parsed.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_filename() == "flyer.pdf"
    assert attachments[0].get_content() == b"%PDF-1.4 data"


def test_build_message_rejects_header_injection_and_no_recipients():
    common = dict(sender="org@example.com", text_body="x", attachments=[])
    with pytest.raises(ValueError):
        build_message(to=["a@example.com"], bcc=[], subject="Hi\r\nBcc: evil@x.com", **common)
    with pytest.raises(ValueError):
        build_message(to=["a@example.com\nBcc: evil@x.com"], bcc=[], subject="Hi", **common)
    with pytest.raises(ValueError):
        build_message(to=[], bcc=["not-an-address"], subject="Hi", **common)
    with pytest.raises(ValueError):
        build_message(to=[], bcc=[], subject="Hi", **common)


def test_message_header_is_case_insensitive():
    message = {"payload": {"headers": [{"name": "From", "value": "A <a@x.com>"}]}}
    assert message_header(message, "from") == "A <a@x.com>"
    assert message_header(message, "Subject") is None
    assert message_header({}, "From") is None


def test_message_text_nested_multipart_without_padding():
    message = {
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/html", "body": {"data": b64("<p>Yes!</p>")}},
                        {"mimeType": "text/plain", "body": {"data": b64("Yes, I'll come ✓")}},
                    ],
                },
                {"mimeType": "text/plain", "filename": "notes.txt", "body": {"attachmentId": "a"}},
            ],
        }
    }
    assert message_text(message) == "Yes, I'll come ✓"


def test_message_text_html_fallback_and_single_part():
    html_only = {
        "payload": {
            "mimeType": "text/html",
            "body": {
                "data": b64("<div>Count me in &amp; +1</div><style>p{}</style><br>Thanks", True)
            },
        }
    }
    assert message_text(html_only) == "Count me in & +1\n\nThanks"
    assert (
        message_text({"payload": {"mimeType": "text/plain", "body": {"data": b64("ok")}}}) == "ok"
    )
    assert message_text({}) == ""


def test_strip_quoted_gmail_two_line_and_outlook():
    gmail = (
        "Yes, see you there!\n\n"
        "On Mon, Nov 2, 2026 at 3:00 PM Organizer <org@example.com>\n"
        "wrote:\n> Will you attend?\n"
    )
    assert strip_quoted(gmail) == "Yes, see you there!"
    single = "Can't make it.\nOn Mon, Nov 2, 2026, Organizer wrote:\nRSVP please"
    assert strip_quoted(single) == "Can't make it."
    outlook = "Maybe.\r\n\r\n________________________________\r\nFrom: Organizer\r\nAttending: yes"
    assert strip_quoted(outlook) == "Maybe."
    original = "No thanks\n-----Original Message-----\nFrom: someone\nI'm attending"
    assert strip_quoted(original) == "No thanks"
    inline = "> Are you coming?\nYes\n>> old\nVegetarian please"
    assert strip_quoted(inline) == "Yes\nVegetarian please"
    assert strip_quoted("On my way, attending!") == "On my way, attending!"


def test_is_forwarded():
    assert is_forwarded("Fwd: Picnic", "")
    assert is_forwarded("FW: Picnic", "")
    assert is_forwarded("fwd:Picnic", "")
    assert is_forwarded("Re: Picnic", "hi\n---------- Forwarded message ---------\nFrom: x")
    assert is_forwarded("Picnic", "Begin forwarded message:\n")
    assert not is_forwarded("Re: Picnic", "Yes I'll come")
    assert not is_forwarded("Fwiw: Picnic", "")


def test_sender_email():
    assert sender_email('"Jane Doe" <Jane.Doe@Example.COM>') == "jane.doe@example.com"
    assert sender_email("plain@x.org") == "plain@x.org"
    assert sender_email("") == ""
