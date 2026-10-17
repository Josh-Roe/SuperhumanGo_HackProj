"""Religious observances from Google Calendar's public holiday feeds (no account or key needed).

Feeds list one all-day entry per local date, 2021 onward, with Google's "tentative" marking.
Jewish feeds already include each holiday's eve; Muslim days also begin at sundown, so those
entries start at noon of the previous local day. Matches prompt organizer review; they never
infer who is attending or certify that no other observance applies.
"""

import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import Field

from hackathon_backend.services.assets.models import BoundaryModel, EventSnapshot

Tradition = Literal["christian", "jewish", "muslim", "hindu", "orthodox_christian"]

# Google's public holiday calendar IDs; each was checked to serve an iCal feed on 2026-10-16.
CALENDAR_IDS: dict[str, str] = {
    "christian": "en.christian#holiday@group.v.calendar.google.com",
    "jewish": "en.judaism#holiday@group.v.calendar.google.com",
    "muslim": "en.islamic#holiday@group.v.calendar.google.com",
    "hindu": "en.hinduism#holiday@group.v.calendar.google.com",
    "orthodox_christian": "en.orthodox_christianity#holiday@group.v.calendar.google.com",
}
ALL_TRADITIONS: tuple[Tradition, ...] = tuple(CALENDAR_IDS)  # type: ignore[assignment]
BEGINS_PREVIOUS_EVENING = {"muslim"}
FEED_URL = "https://calendar.google.com/calendar/ical/{id}/public/basic.ics"
CACHE_SECONDS = 12 * 3600
MAX_FEED_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 10.0


class HolidayEntry(BoundaryModel):
    name: str
    first_day: date
    end_day: date  # exclusive, as in iCal DTEND
    tentative: bool = False


class Feed(BoundaryModel):
    tradition: str
    calendar_name: str
    url: str
    fetched_at: datetime
    entries: tuple[HolidayEntry, ...]


class CalendarObservance(BoundaryModel):
    name: str
    tradition: str
    starts_at: datetime
    ends_at: datetime


class CalendarCheck(BoundaryModel):
    """Feeds consulted for one event window. `unavailable` lists traditions that failed."""

    feeds: tuple[Feed, ...] = Field(default=(), exclude=True)
    observances: tuple[CalendarObservance, ...] = ()
    unavailable: tuple[str, ...] = ()


def feed_url(tradition: str) -> str:
    calendar_id = CALENDAR_IDS[tradition]
    return FEED_URL.format(id=calendar_id.replace("#", "%23").replace("@", "%40"))


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";")
    ).replace("\\\\", "\\")


def _day(value: str) -> date | None:
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        return None


def parse_feed(text: str) -> tuple[str, tuple[HolidayEntry, ...]]:
    """Calendar name plus all-day entries; timed or malformed entries are skipped."""
    name, entries, current = "", [], None
    for line in _unfold(text):
        key, _, value = line.partition(":")
        prop = key.split(";", 1)[0].upper()
        if prop == "X-WR-CALNAME" and current is None:
            name = _unescape(value).strip()
        elif prop == "BEGIN" and value == "VEVENT":
            current = {}
        elif prop == "END" and value == "VEVENT" and current is not None:
            first = current.get("first")
            summary = current.get("summary", "").strip()
            if isinstance(first, date) and summary:
                end = current.get("end")
                entries.append(
                    HolidayEntry(
                        name=summary,
                        first_day=first,
                        end_day=end
                        if isinstance(end, date) and end > first
                        else first + timedelta(days=1),
                        tentative="tentative" in current.get("description", "").casefold(),
                    )
                )
            current = None
        elif current is not None:
            if prop == "DTSTART" and "VALUE=DATE" in key.upper():
                current["first"] = _day(value)
            elif prop == "DTEND" and "VALUE=DATE" in key.upper():
                current["end"] = _day(value)
            elif prop == "SUMMARY":
                current["summary"] = _unescape(value)
            elif prop == "DESCRIPTION":
                current["description"] = _unescape(value)
    return name, tuple(entries)


def local_interval(
    entry: HolidayEntry, tradition: str, zone: ZoneInfo
) -> tuple[datetime, datetime]:
    starts = datetime.combine(entry.first_day, clock(), zone)
    if tradition in BEGINS_PREVIOUS_EVENING:
        starts -= timedelta(hours=12)
    return starts, datetime.combine(entry.end_day, clock(), zone)


class HolidayCalendar:
    """Fetches and caches public feeds per process. Inject `transport` in tests."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        clock_seconds=time.monotonic,
    ) -> None:
        self._transport = transport
        self._clock = clock_seconds
        self._cache: dict[str, tuple[float, Feed]] = {}

    async def feed(self, tradition: str) -> Feed:
        cached = self._cache.get(tradition)
        if cached and self._clock() - cached[0] < CACHE_SECONDS:
            return cached[1]
        url = feed_url(tradition)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_SECONDS),
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            response = await client.get(url)
        response.raise_for_status()
        if len(response.content) > MAX_FEED_BYTES:
            raise ValueError("holiday feed too large")
        name, entries = parse_feed(response.text)
        if not entries:
            raise ValueError("holiday feed has no entries")
        feed = Feed(
            tradition=tradition,
            calendar_name=name or tradition,
            url=url,
            fetched_at=datetime.now(UTC),
            entries=entries,
        )
        self._cache[tradition] = (self._clock(), feed)
        return feed

    async def check(self, event: EventSnapshot, traditions: tuple[str, ...]) -> CalendarCheck:
        zone = ZoneInfo(event.timezone)
        feeds, observances, unavailable = [], [], []
        for tradition in dict.fromkeys(traditions):
            try:
                feed = await self.feed(tradition)
            except (httpx.HTTPError, ValueError):
                unavailable.append(tradition)
                continue
            feeds.append(feed)
            for entry in feed.entries:
                starts, ends = local_interval(entry, tradition, zone)
                if event.starts_at < ends and starts < event.ends_at:
                    label = entry.name
                    if entry.tentative and "tentative" not in label.casefold():
                        label += " (tentative date)"
                    observances.append(
                        CalendarObservance(
                            name=label, tradition=tradition, starts_at=starts, ends_at=ends
                        )
                    )
        return CalendarCheck(
            feeds=tuple(feeds), observances=tuple(observances), unavailable=tuple(unavailable)
        )
