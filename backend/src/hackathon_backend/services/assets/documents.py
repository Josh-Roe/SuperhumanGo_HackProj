"""Accessible HTML rendering of already generated Go prose; no LLM substitution."""

from html import escape

from hackathon_backend.services.assets.models import EventSnapshot, GoContent, require_scope


def render_event_document(
    event: EventSnapshot,
    document: GoContent,
    *,
    owner_id: str,
    summary: GoContent | None = None,
) -> bytes:
    require_scope(event, owner_id, document, *((summary,) if summary else ()))
    if document.kind != "event_document" or (
        summary is not None and summary.kind != "plain_language_summary"
    ):
        raise ValueError("Expected Go event-document prose and optional Go summary")

    def paragraphs(text: str) -> str:
        return "".join(
            f"<p>{escape(block).replace(chr(10), '<br>')}</p>"
            for block in text.split("\n\n")
            if block.strip()
        )

    fields = event.flyer_fields()
    summary_html = (
        ""
        if summary is None
        else (
            '<section aria-labelledby="summary"><h2 id="summary">Plain-language summary</h2>'
            f"{paragraphs(summary.body)}</section>"
        )
    )
    html = f"""<!doctype html>
<html lang="{escape(document.language)}" dir="auto">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>{escape(event.title)}</title><style>
body{{font:1.125rem/1.65 system-ui,sans-serif;color:#172333;background:#fff;
max-width:48rem;margin:2rem auto;padding:0 1.25rem;overflow-wrap:anywhere}}
h1{{font-size:2rem;line-height:1.2}}dt{{font-weight:700}}dd{{margin:0 0 1rem}}
footer{{border-top:1px solid #abb4bf;margin-top:2rem;padding-top:1rem;font-size:1rem}}
@media print{{body{{margin:0;max-width:none}}}}
</style></head><body><main><h1>{escape(event.title)}</h1>
<dl><dt>Date and time</dt><dd>{escape(fields["when"])}</dd>
<dt>Location</dt><dd>{escape(event.location)}</dd></dl>
{summary_html}<section aria-labelledby="details"><h2 id="details">Event details</h2>
{paragraphs(document.body)}</section></main>
<footer>Event revision {event.revision}. Prose source: Superhuman Go.
Generation reference: {escape(document.generation_id)}.</footer></body></html>"""
    return html.encode("utf-8")
