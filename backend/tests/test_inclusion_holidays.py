import asyncio
from datetime import date

import httpx
from test_assets_support import event

from hackathon_backend.services.inclusion import (
    HolidayCalendar,
    InclusionInput,
    check_inclusion,
)
from hackathon_backend.services.inclusion.holidays import CALENDAR_IDS, feed_url, parse_feed


def ics(name, *entries):
    events = "".join(
        "BEGIN:VEVENT\r\n"
        f"DTSTART;VALUE=DATE:{day}\r\n"
        f"DTEND;VALUE=DATE:{end}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description}\r\n"
        "END:VEVENT\r\n"
        for day, end, summary, description in entries
    )
    return f"BEGIN:VCALENDAR\r\nX-WR-CALNAME:{name}\r\n{events}END:VCALENDAR\r\n"


# Synthetic feeds; event() is 2026-10-16 18:00-19:00 America/Los_Angeles.
FEEDS = {
    "jewish": ics(
        "Jewish Holidays",
        ("20261016", "20261017", "Synthetic Festival Eve", "Observance"),
        # 2026-10-17 starts after the event locally, though the event ends 10-17 UTC.
        ("20261017", "20261018", "Synthetic Festival", "Observance"),
    ),
    "muslim": ics(
        "Muslim Holidays",
        ("20261017", "20261018", "Synthetic Eid", "Date is tentative and may change."),
    ),
    "hindu": ics("Hindu Holidays", ("20261015", "20261016", "Synthetic Day Before", "")),
    "christian": ics("Christian Holidays", ("20261101", "20261102", "Synthetic Feast", "")),
    "orthodox_christian": ics("Orthodox Holidays", ("20270107", "20270108", "Synthetic", "")),
}
BY_URL = {feed_url(tradition): body for tradition, body in FEEDS.items()}


def calendar(failing=(), calls=None):
    def handler(request):
        url = str(request.url)
        if calls is not None:
            calls.append(url)
        if any(url == feed_url(t) for t in failing):
            return httpx.Response(503)
        return httpx.Response(200, text=BY_URL[url])

    return HolidayCalendar(transport=httpx.MockTransport(handler))


def religious(report):
    return next(f for f in report.findings if f.category == "religious_observances")


def run(holidays, facts=None):
    snapshot = event()
    facts = facts or InclusionInput()
    check = asyncio.run(holidays.check(snapshot, facts.traditions))
    return check, religious(
        check_inclusion(snapshot, facts, owner_id=snapshot.owner_id, calendar=check)
    )


def test_feed_ids_are_google_public_holiday_calendars():
    assert set(CALENDAR_IDS) == {"christian", "jewish", "muslim", "hindu", "orthodox_christian"}
    assert feed_url("jewish") == (
        "https://calendar.google.com/calendar/ical/"
        "en.judaism%23holiday%40group.v.calendar.google.com/public/basic.ics"
    )


def test_parse_unfolds_unescapes_and_skips_timed_entries():
    text = (
        "BEGIN:VCALENDAR\r\nX-WR-CALNAME:Synthetic\r\n"
        "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261224\r\nDTEND;VALUE=DATE:20261225\r\n"
        "SUMMARY:Long\\, folded\r\n  name\r\nDESCRIPTION:Date is tentative\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nDTSTART:20261224T100000Z\r\nSUMMARY:Timed\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    name, entries = parse_feed(text)
    assert name == "Synthetic" and len(entries) == 1
    assert entries[0].name == "Long, folded name" and entries[0].tentative
    assert (entries[0].first_day, entries[0].end_day) == (date(2026, 12, 24), date(2026, 12, 25))


def test_local_dates_and_sundown_start_find_conflicts_with_sources():
    _, finding = run(calendar())
    assert finding.status == "attention" and finding.reason == "overlap_with_observance"
    # Muslim days begin the previous evening; the next-day Jewish entry and the
    # previous-day Hindu entry do not overlap in the event's own timezone.
    assert finding.conflicts == ("Synthetic Festival Eve", "Synthetic Eid (tentative date)")
    assert {s.label for s in finding.sources} == {
        f"Google Calendar public holidays: {name}"
        for name in (
            "Jewish Holidays",
            "Muslim Holidays",
            "Hindu Holidays",
            "Christian Holidays",
            "Orthodox Holidays",
        )
    }
    assert all(str(s.url).startswith("https://calendar.google.com/") for s in finding.sources)


def test_no_overlap_in_selected_calendars_is_recorded():
    _, finding = run(calendar(), InclusionInput(traditions=("christian", "hindu")))
    assert finding.status == "recorded" and finding.conflicts == ()
    assert len(finding.sources) == 2


def test_unavailable_feed_stays_unknown_unless_another_feed_conflicts():
    check, finding = run(
        calendar(failing=("christian",)), InclusionInput(traditions=("christian",))
    )
    assert check.unavailable == ("christian",)
    assert finding.status == "unknown" and finding.reason == "holiday_calendar_unavailable"
    _, finding = run(
        calendar(failing=("christian",)), InclusionInput(traditions=("christian", "jewish"))
    )
    assert finding.status == "attention"


def test_calendar_not_run_is_unknown_and_opt_out_asks_for_selection():
    snapshot = event()
    report = check_inclusion(snapshot, InclusionInput(), owner_id=snapshot.owner_id)
    assert religious(report).reason == "holiday_calendar_unavailable"
    report = check_inclusion(snapshot, InclusionInput(traditions=()), owner_id=snapshot.owner_id)
    assert religious(report).reason == "select_relevant_observances"


def test_feeds_are_cached_between_checks():
    calls = []
    holidays = calendar(calls=calls)
    run(holidays)
    run(holidays)
    assert len(calls) == len(FEEDS)
