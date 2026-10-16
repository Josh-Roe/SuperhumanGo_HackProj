"""RFC 5322 message building and Gmail message parsing for invitations and RSVP replies."""

import base64
import binascii
import html
import re
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any

_ON_WROTE = re.compile(r"^\s*On\b.*\bwrote:\s*$", re.IGNORECASE)
_OUTLOOK_SEPARATORS = ("-----Original Message-----", "________________________________")
_FORWARD_MARKERS = ("---------- Forwarded message ---------", "Begin forwarded message:")
_FORWARD_SUBJECT = re.compile(r"^\s*fwd?\s*:", re.IGNORECASE)


def _check_header(value: str, field: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError(f"{field} must not contain line breaks")
    return value


def _check_address(value: str, field: str) -> str:
    _check_header(value, field)
    if "@" not in parseaddr(value)[1]:
        raise ValueError(f"{field} must be an email address")
    return value


def build_message(
    *,
    sender: str,
    to: list[str],
    bcc: list[str],
    subject: str,
    text_body: str,
    attachments: list[tuple[str, str, bytes]],
    headers: dict[str, str] | None = None,
) -> bytes:
    """Plain-text message; Bcc stays in the raw bytes because Gmail strips it on send."""
    if not to and not bcc:
        raise ValueError("message needs at least one recipient")
    message = EmailMessage(policy=SMTP)
    message["From"] = _check_address(sender, "sender")
    if to:
        message["To"] = ", ".join(_check_address(address, "to") for address in to)
    if bcc:
        message["Bcc"] = ", ".join(_check_address(address, "bcc") for address in bcc)
    message["Subject"] = _check_header(subject, "subject")
    for name, value in (headers or {}).items():
        _check_header(name, "header name")
        message[name] = _check_header(value, name)
    message.set_content(text_body)
    for filename, mime_type, data in attachments:
        _check_header(filename, "attachment filename")
        maintype, _, subtype = mime_type.partition("/")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return message.as_bytes()


def message_header(message: dict[str, Any], name: str) -> str | None:
    wanted = name.lower()
    for header in message.get("payload", {}).get("headers", []) or []:
        if str(header.get("name", "")).lower() == wanted:
            return header.get("value")
    return None


def _decode(data: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (binascii.Error, ValueError):
        return b""


def _charset(part: dict[str, Any]) -> str:
    for header in part.get("headers", []) or []:
        if str(header.get("name", "")).lower() == "content-type":
            match = re.search(r'charset="?([\w.-]+)"?', str(header.get("value", "")), re.I)
            if match:
                return match.group(1)
    return "utf-8"


def _part_text(part: dict[str, Any]) -> str:
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    raw = _decode(data)
    try:
        return raw.decode(_charset(part), errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _walk(part: dict[str, Any]):
    yield part
    for child in part.get("parts", []) or []:
        if isinstance(child, dict):
            yield from _walk(child)


class _TextExtractor(HTMLParser):
    _BLOCK = {"br", "p", "div", "li", "tr", "blockquote", "h1", "h2", "h3"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in self._BLOCK:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.chunks.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    lines = (" ".join(line.split()) for line in html.unescape("".join(parser.chunks)).split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def message_text(message: dict[str, Any]) -> str:
    """text/plain body of a Gmail format=full message, else stripped text/html."""
    payload = message.get("payload") or {}
    parts = list(_walk(payload))
    for mime_type, convert in (("text/plain", str), ("text/html", html_to_text)):
        texts = [
            _part_text(part)
            for part in parts
            if part.get("mimeType") == mime_type and not part.get("filename")
        ]
        texts = [text for text in texts if text]
        if texts:
            return convert(texts[0])
    return ""


def strip_quoted(text: str) -> str:
    """Drop quoted history: '>' lines and everything after a reply/Outlook separator."""
    lines = text.replace("\r\n", "\n").split("\n")
    kept: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in _OUTLOOK_SEPARATORS or stripped.startswith(_OUTLOOK_SEPARATORS[1]):
            break
        if _ON_WROTE.match(line):
            break
        if re.match(r"^\s*On\b", line) and index + 1 < len(lines):
            if _ON_WROTE.match(f"{line} {lines[index + 1].strip()}"):
                break
        if stripped.startswith(">"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def is_forwarded(subject: str, text: str) -> bool:
    return bool(_FORWARD_SUBJECT.match(subject or "")) or any(
        marker in (text or "") for marker in _FORWARD_MARKERS
    )


def sender_email(from_header: str) -> str:
    return parseaddr(from_header or "")[1].strip().lower()
