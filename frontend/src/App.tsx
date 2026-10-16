import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ApiError,
  authConfigured,
  createLiveGateway,
  loadProjectStatus,
  signIn,
} from "./api";
import { createPreviewGateway } from "./preview";
import { emptyFacts, factLabels, friendlyState, safeUrl } from "./types";
import type {
  Content,
  EventGateway,
  EventInput,
  EventRecord,
  FactKey,
  Session,
  WorkspaceEvent,
} from "./types";
import { eventDate, localTime, toInstant } from "./dates";
import "./App.css";

type Page =
  "dashboard" | "details" | "review" | "distribution" | "updates" | "rsvps";
const pages: { id: Page; name: string; icon: string }[] = [
  { id: "dashboard", name: "Overview", icon: "▦" },
  { id: "details", name: "Event details", icon: "◷" },
  { id: "review", name: "Design & inclusion", icon: "◇" },
  { id: "distribution", name: "Distribution", icon: "↗" },
  { id: "updates", name: "Updates & sync", icon: "↻" },
  { id: "rsvps", name: "RSVPs", icon: "♧" },
];
const contentLabels: Record<Content["kind"], string> = {
  description: "Event description",
  plain_language_summary: "Plain-language summary",
  invitation: "Invitation",
  change_notice: "Change notice",
  event_document: "Event document",
};
function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function ExternalLink({
  url,
  children,
}: {
  url?: string;
  children: ReactNode;
}) {
  const href = safeUrl(url);
  return href ? (
    <a href={href} target="_blank" rel="noreferrer">
      {children} ↗
    </a>
  ) : null;
}
function Login({
  onEnter,
}: {
  onEnter: (gateway: EventGateway, session?: Session) => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const session = await signIn(
        String(data.get("email")),
        String(data.get("password")),
      );
      onEnter(createLiveGateway(session.access_token), session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <a className="wordmark" href="#login">
          <span className="brand-icon">↗</span> EVENT WORKSPACE
        </a>
        <div>
          <p className="eyebrow">
            A LITTLE LESS ORGANIZING. A LOT MORE TOGETHER.
          </p>
          <h1>
            Good things
            <br />
            start with
            <br />
            <em>a gathering.</em>
          </h1>
          <p>
            Tell Superhuman Go what you’re planning. Bring the details, writing,
            and people together here.
          </p>
          <div className="story-steps">
            <span>01 · Plan with Go</span>
            <span>02 · Make it yours</span>
            <span>03 · Bring people together</span>
          </div>
        </div>
        <p className="small">
          Your events. Your review. Your decision to send.
        </p>
      </section>
      <section className="login-form">
        <p className="eyebrow">YOUR ORGANIZER WORKSPACE</p>
        <h2>Welcome in.</h2>
        <p>
          Sign in to review the events Go creates for you, or start one
          yourself.
        </p>
        <form onSubmit={submit}>
          <label>
            Email
            <input
              name="email"
              type="email"
              autoComplete="username"
              required
              disabled={busy || !authConfigured}
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              disabled={busy || !authConfigured}
            />
          </label>
          {error && (
            <p role="alert" className="error-box">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy || !authConfigured}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        {!authConfigured && (
          <p className="notice">
            Live sign-in is awaiting a connected organizer account.
          </p>
        )}
        <div className="preview-entry">
          <span className="eyebrow">EXPLORE THE EXPERIENCE</span>
          <p>
            Try a sample event. Preview changes stay in this tab and disappear
            when you leave. No accounts connect and no invitations send.
          </p>
          <button
            className="secondary"
            onClick={() => onEnter(createPreviewGateway())}
          >
            Open local preview <span aria-hidden="true">↗</span>
          </button>
        </div>
      </section>
    </main>
  );
}
function Details({
  record,
  onSave,
  busy,
  onDirty,
}: {
  record: WorkspaceEvent | null;
  onSave: (input: EventInput) => void;
  busy: boolean;
  onDirty: () => void;
}) {
  const event = record?.event;
  const [formError, setFormError] = useState("");
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError("");
    const data = new FormData(e.currentTarget);
    try {
      const timezone = String(data.get("timezone")).trim();
      const starts_at = toInstant(String(data.get("start")), timezone),
        ends_at = toInstant(String(data.get("end")), timezone);
      if (Date.parse(ends_at) <= Date.parse(starts_at))
        throw new Error("End time must be after start time.");
      const emails = [
        ...new Set(
          String(data.get("invitees"))
            .split(/[\s,;]+/)
            .filter(Boolean)
            .map((email) => email.toLowerCase()),
        ),
      ];
      if (emails.some((email) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)))
        throw new Error(
          "Check each invitee email address. Separate addresses with commas or new lines.",
        );
      const links = String(data.get("links"))
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      if (links.some((link) => !safeUrl(link)))
        throw new Error("Use a full HTTPS address for each event link.");
      onSave({
        title: String(data.get("title")).trim(),
        description: String(data.get("description")).trim(),
        location: String(data.get("location")).trim(),
        starts_at,
        ends_at,
        timezone,
        organizer_contact: String(data.get("contact")).trim(),
        links,
        invitees: emails.map((email) => ({
          id:
            event?.invitees.find((i) => i.email === email)?.id ??
            crypto.randomUUID(),
          email,
        })),
      });
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Check the event details.",
      );
    }
  }
  return (
    <form className="panel details-form" onSubmit={submit} onChange={onDirty}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">01 / THE PLAN</p>
          <h2>
            {event
              ? "Every detail, in one place."
              : "What are you bringing people together for?"}
          </h2>
        </div>
        {event && <Badge>Revision {event.revision}</Badge>}
      </div>
      <p className="muted">
        Go can create these details through the website’s MCP tools. You can
        always edit them here.
      </p>
      <fieldset disabled={busy}>
        <label>
          Event title
          <input
            name="title"
            required
            maxLength={200}
            defaultValue={event?.title}
            placeholder="Give your gathering a name"
          />
        </label>
        <div className="form-grid">
          <label>
            Location or online meeting link
            <input
              name="location"
              required
              defaultValue={event?.location}
              placeholder="Venue, address, or meeting URL"
            />
          </label>
          <label>
            Organizer email
            <input
              name="contact"
              type="email"
              required
              defaultValue={event?.organizer_contact}
              placeholder="you@example.com"
            />
          </label>
        </div>
        <div className="form-grid three">
          <label>
            Start time
            <input
              name="start"
              type="datetime-local"
              required
              defaultValue={
                event ? localTime(event.starts_at, event.timezone) : ""
              }
            />
          </label>
          <label>
            End time
            <input
              name="end"
              type="datetime-local"
              required
              defaultValue={
                event ? localTime(event.ends_at, event.timezone) : ""
              }
            />
          </label>
          <label>
            Timezone
            <input
              name="timezone"
              required
              defaultValue={
                event?.timezone ??
                Intl.DateTimeFormat().resolvedOptions().timeZone
              }
              placeholder="America/Los_Angeles"
              aria-describedby="timezone-hint"
            />
          </label>
        </div>
        <p id="timezone-hint" className="small muted">
          Times use the named IANA timezone. Daylight-saving clock changes are
          checked before saving.
        </p>
        <label>
          Organizer description
          <textarea
            name="description"
            rows={4}
            defaultValue={event?.description}
            placeholder="Your notes for Go. Review Go’s writing in the next step."
          />
        </label>
        <label>
          Relevant links{" "}
          <span className="optional">· one HTTPS URL per line</span>
          <textarea
            name="links"
            rows={2}
            defaultValue={event?.links.join("\n")}
          />
        </label>
        <label>
          Invitee emails{" "}
          <span className="optional">· private to the organizer</span>
          <textarea
            name="invitees"
            rows={3}
            defaultValue={event?.invitees.map((i) => i.email).join("\n")}
            placeholder="Separate addresses with commas or new lines"
          />
        </label>
      </fieldset>
      {formError && (
        <p role="alert" className="error-box">
          {formError}
        </p>
      )}
      <div className="action-row">
        <p className="small muted">
          Saving changes creates a new revision. Earlier material becomes stale.
        </p>
        <button className="primary" disabled={busy}>
          {busy ? "Saving…" : "Save & continue"}
        </button>
      </div>
    </form>
  );
}
function Review({
  record,
  busy,
  onPrepare,
  onReview,
  onDirty,
}: {
  record: WorkspaceEvent;
  busy: boolean;
  onPrepare: () => void;
  onReview: (content: Content[], facts: WorkspaceEvent["facts"]) => void;
  onDirty: () => void;
}) {
  const [content, setContent] = useState(record.content);
  const [facts, setFacts] = useState(record.facts ?? emptyFacts());
  const [ack, setAck] = useState(false);
  const [error, setError] = useState("");
  const currentContent = content.filter(
    (c) => c.event_revision === record.event.revision,
  );
  function save(e: FormEvent) {
    e.preventDefault();
    if (
      Object.values(facts).some(
        (f) => f.value !== "unknown" && (!f.source.trim() || !f.confirmed_on),
      )
    ) {
      setError(
        "Add a source and confirmation date for every yes/no fact, or keep it unknown.",
      );
      return;
    }
    if (currentContent.some((c) => !c.body.trim())) {
      setError(
        "Writing previews cannot be empty. Restore the text or request preparation again.",
      );
      return;
    }
    onReview(
      content.map((c) =>
        c.event_revision === record.event.revision
          ? { ...c, state: "ready" }
          : c,
      ),
      facts,
    );
  }
  return (
    <form onSubmit={save} onChange={onDirty}>
      <section className="go-banner">
        <span className="go-symbol" aria-hidden="true">
          ✳
        </span>
        <div>
          <p className="eyebrow">YOUR WRITING & COORDINATION AGENT</p>
          <h2>Your writing, coordinated by Go.</h2>
          <p>
            Go writes through its own agent and saves work through our MCP
            tools. New work waits until your Go session processes it.
          </p>
        </div>
        <button
          className="secondary"
          type="button"
          disabled={busy}
          onClick={onPrepare}
        >
          Request preparation
        </button>
      </section>
      <div className="work-queue" aria-label="Go preparation status">
        {record.work.map((work) => (
          <p className="small" key={work.id}>
            <Badge
              tone={
                work.event_revision !== record.event.revision ||
                work.state === "failed"
                  ? "warning"
                  : ""
              }
            >
              {work.event_revision !== record.event.revision
                ? "Stale"
                : friendlyState(work.state)}
            </Badge>{" "}
            Go preparation · revision {work.event_revision}
          </p>
        ))}
      </div>
      <div className="two-column">
        <section className="panel">
          <p className="eyebrow">02 / MAKE IT YOURS</p>
          <h2>Words worth reviewing.</h2>
          <p className="muted">
            Edit before approving. Organizer edits are labeled. Grammarly
            assistance can be used in a supported writing client; it is
            unverified here.
          </p>
          {content.length === 0 && (
            <div className="empty">
              <h3>Waiting for Go’s first draft</h3>
              <p>
                No writing has been returned yet. Ask Go to process your event
                work.
              </p>
            </div>
          )}
          {content.map((c, i) => (
            <label key={c.id} className="content-editor">
              <span className="spread">
                {contentLabels[c.kind]}
                <Badge
                  tone={
                    c.event_revision !== record.event.revision ? "warning" : ""
                  }
                >
                  {c.event_revision !== record.event.revision
                    ? `Stale · r${c.event_revision}`
                    : friendlyState(c.state)}
                </Badge>
              </span>
              <span className="small muted">
                {c.producer === "superhuman_go"
                  ? "Superhuman Go"
                  : c.producer === "gemini"
                    ? "Gemini-assisted portion"
                    : "Edited by organizer"}{" "}
                · revision {c.event_revision}
              </span>
              <textarea
                rows={
                  c.kind === "invitation" || c.kind === "event_document" ? 7 : 4
                }
                value={c.body}
                disabled={busy || c.event_revision !== record.event.revision}
                onChange={(e) =>
                  setContent((all) =>
                    all.map((item, index) =>
                      index === i
                        ? {
                            ...item,
                            body: e.target.value,
                            producer: "organizer",
                            state: "needs_review",
                          }
                        : item,
                    ),
                  )
                }
              />
            </label>
          ))}
        </section>
        <aside className="asset-column">
          <section className="panel">
            <p className="eyebrow">CANVA & DOCUMENTS</p>
            <h2>The shape of your event.</h2>
            {(["flyer", "document"] as const).map((kind) => {
              const asset = record.assets.find((a) => a.kind === kind);
              return (
                <div className="asset" key={kind}>
                  <div className="asset-preview">
                    {asset && safeUrl(asset.preview_url) && kind === "flyer" ? (
                      <img
                        src={safeUrl(asset.preview_url)}
                        alt={
                          asset.alt_text ||
                          "Flyer preview; accessible text awaits review"
                        }
                      />
                    ) : (
                      <span aria-hidden="true">
                        {kind === "flyer" ? "◇" : "≡"}
                      </span>
                    )}
                  </div>
                  <h3>
                    {kind === "flyer" ? "Custom Canva flyer" : "Event document"}
                  </h3>
                  <p className="small muted">
                    {asset
                      ? `Revision ${asset.event_revision} · ${asset.event_revision !== record.event.revision ? "stale" : friendlyState(asset.state)}`
                      : "Awaiting an actual artifact. No preview available."}
                  </p>
                  <ExternalLink url={asset?.edit_url}>
                    Edit in Canva
                  </ExternalLink>
                  <ExternalLink url={asset?.current_url}>
                    Open current {kind}
                  </ExternalLink>
                  {asset?.alt_text && <p className="small">{asset.alt_text}</p>}
                </div>
              );
            })}
          </section>
        </aside>
      </div>
      <section className="panel inclusion">
        <p className="eyebrow">INCLUSION / ORGANIZER REVIEW</p>
        <h2>Make room for everyone.</h2>
        <p className="muted">
          Confirm what you know. Keep everything else unknown. This review does
          not certify the venue. Individual dietary and access needs stay
          private.
        </p>
        <div className="fact-grid">
          {(Object.entries(factLabels) as [FactKey, string][]).map(
            ([key, label]) => (
              <fieldset key={key} className="fact" disabled={busy}>
                <legend>{label}</legend>
                <label className="small">
                  Confirmed availability
                  <select
                    aria-label={`${label}: availability`}
                    value={facts[key].value}
                    onChange={(e) =>
                      setFacts((all) => ({
                        ...all,
                        [key]: {
                          ...all[key],
                          value: e.target.value as "yes" | "no" | "unknown",
                        },
                      }))
                    }
                  >
                    <option value="unknown">Unknown / not checked</option>
                    <option value="yes">Yes · organizer confirmed</option>
                    <option value="no">No · organizer confirmed</option>
                  </select>
                </label>
                <label className="small">
                  {key === "observances"
                    ? "Which observances should be checked? Include dated sources."
                    : "Details and follow-up questions"}
                  <textarea
                    rows={2}
                    value={facts[key].detail}
                    onChange={(e) =>
                      setFacts((all) => ({
                        ...all,
                        [key]: { ...all[key], detail: e.target.value },
                      }))
                    }
                  />
                </label>
                <label className="small">
                  Source / confirmed by
                  <input
                    value={facts[key].source}
                    onChange={(e) =>
                      setFacts((all) => ({
                        ...all,
                        [key]: { ...all[key], source: e.target.value },
                      }))
                    }
                  />
                </label>
                <label className="small">
                  Confirmation date
                  <input
                    type="date"
                    value={facts[key].confirmed_on}
                    onChange={(e) =>
                      setFacts((all) => ({
                        ...all,
                        [key]: { ...all[key], confirmed_on: e.target.value },
                      }))
                    }
                  />
                </label>
              </fieldset>
            ),
          )}
        </div>
        {record.findings.length > 0 && (
          <div className="findings">
            <h3>Inclusion findings</h3>
            {record.findings.map((f, i) => (
              <article key={i}>
                <Badge>{friendlyState(f.status)}</Badge>
                <strong>{f.category}</strong>
                <p>{friendlyState(f.reason)}</p>
                {f.sources.map((s, n) => (
                  <p className="small" key={n}>
                    {s.reference} · checked {s.checked_on}
                  </p>
                ))}
              </article>
            ))}
          </div>
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            required
          />
          I reviewed this revision’s writing, design, and inclusion questions,
          including unresolved unknowns.
        </label>
        {error && (
          <p role="alert" className="error-box">
            {error}
          </p>
        )}
        <div className="action-row">
          <p className="small muted">
            Review saves your changes. Sending requires a separate confirmation.
          </p>
          <button
            className="primary"
            disabled={busy || !ack || currentContent.length === 0}
          >
            Save review & continue
          </button>
        </div>
      </section>
    </form>
  );
}
function SyncStatus({ record }: { record: WorkspaceEvent }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">PROVIDER RECEIPTS</p>
          <h2>Every part has a status.</h2>
        </div>
        <Badge>Current · r{record.event.revision}</Badge>
      </div>
      <div className="sync-grid">
        {["Superhuman Go", "Calendar", "Gmail", "Canva", "Documents"].map(
          (provider) => {
            const op = record.operations
              .filter((o) => o.provider === provider)
              .at(-1);
            const asset = record.assets.find(
              (a) => a.kind === (provider === "Canva" ? "flyer" : "document"),
            );
            const work = record.work
              .filter((w) => w.event_revision === record.event.revision)
              .at(-1);
            const status =
              op ??
              (provider === "Superhuman Go"
                ? work
                : ["Canva", "Documents"].includes(provider)
                  ? asset
                  : undefined);
            const stale =
              status && status.event_revision !== record.event.revision;
            return (
              <article className="sync-item" key={provider}>
                <h3>{provider}</h3>
                <Badge
                  tone={stale || status?.state === "failed" ? "warning" : ""}
                >
                  {stale
                    ? "Stale"
                    : status
                      ? friendlyState(status.state)
                      : "Not prepared"}
                </Badge>
                <p className="small muted">
                  {status
                    ? `Revision ${status.event_revision}`
                    : "No receipt received"}
                </p>
                {op?.error_code && (
                  <p className="small error-text">
                    {friendlyState(op.error_code)}
                  </p>
                )}
                {op?.receipt && <p className="small receipt">{op.receipt}</p>}
              </article>
            );
          },
        )}
      </div>
    </section>
  );
}
function Distribution({
  record,
  busy,
  preview,
  onPublish,
}: {
  record: WorkspaceEvent;
  busy: boolean;
  preview: boolean;
  onPublish: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const sent = Boolean(record.gmail?.sent);
  const kind = sent ? "change_notice" : "invitation";
  const mail = record.content.find(
    (c) =>
      c.kind === kind &&
      c.event_revision === record.event.revision &&
      c.state === "ready",
  );
  const readyAssets = ["flyer", "document"].every((kind) =>
    record.assets.some(
      (a) =>
        a.kind === kind &&
        a.event_revision === record.event.revision &&
        ["ready", "succeeded"].includes(a.state),
    ),
  );
  const reviewed =
    record.review_revision === record.event.revision && !!mail && readyAssets;
  return (
    <>
      <div className="two-column">
        <section className="panel">
          <p className="eyebrow">03 / BRING PEOPLE TOGETHER</p>
          <h2>
            {sent
              ? "A fresh notice for a new plan."
              : "One last look before it goes."}
          </h2>
          <p className="muted">
            {sent
              ? "The previous invitation was sent. This update needs a new change-notification draft. Sent email and attachments remain unchanged."
              : record.gmail?.draft_id
                ? "Your invitation is unsent. Preparation replaces the existing draft; sending requires your approval."
                : "A reviewed invitation will be prepared for Gmail and Calendar."}
          </p>
          <div className="mail-preview">
            <div className="mail-header">
              <Badge>
                Gmail · {sent ? "New notification" : "Invitation draft"}
              </Badge>
              <p className="small">
                To: {record.event.invitees.length} invited{" "}
                {record.event.invitees.length === 1 ? "person" : "people"} ·
                private recipients
              </p>
              <strong>{record.event.title}</strong>
            </div>
            <div className="mail-body">
              {mail?.body ??
                `Awaiting reviewed ${sent ? "change notice" : "invitation"} for revision ${record.event.revision}.`}
            </div>
            <div className="mail-footer">
              Current event and flyer links are supplied by the backend.
              Attached files are revision snapshots.
            </div>
          </div>
        </section>
        <section className="panel">
          <p className="eyebrow">PUBLISH CHECKLIST</p>
          <h2>Your call to send.</h2>
          <ul className="checklist">
            <li>
              {record.review_revision === record.event.revision ? "✓" : "○"}{" "}
              Writing and inclusion reviewed for r{record.event.revision}
            </li>
            <li>
              {mail ? "✓" : "○"} Current {sent ? "change notice" : "invitation"}{" "}
              approved
            </li>
            <li>{readyAssets ? "✓" : "○"} Current flyer and document ready</li>
            <li>
              {record.event.invitees.length ? "✓" : "○"}{" "}
              {record.event.invitees.length} invitees selected
            </li>
          </ul>
          <p className="notice">
            {preview
              ? "Local preview: publish is disabled. No provider is connected and no email can be sent."
              : "This action authorizes Calendar invitations and Gmail delivery for the exact reviewed revision. Partial failures remain visible below."}
          </p>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              disabled={preview || !reviewed || busy}
            />
            I confirm the current event, recipients, and material, and authorize{" "}
            {sent ? "sending this update" : "publishing this invitation"}.
          </label>
          <button
            className="primary full-width"
            disabled={
              busy ||
              preview ||
              !reviewed ||
              !confirmed ||
              !record.event.invitees.length
            }
            onClick={onPublish}
          >
            {busy
              ? "Requesting…"
              : sent
                ? "Confirm & send update"
                : "Confirm & publish"}
          </button>
          {!reviewed && (
            <p className="small muted">
              Complete the current writing, artifact, and inclusion review to
              continue.
            </p>
          )}
        </section>
      </div>
      <SyncStatus record={record} />
    </>
  );
}
function Rsvps({ record }: { record: WorkspaceEvent }) {
  return (
    <section className="panel">
      <p className="eyebrow">PRIVATE / ORGANIZER ONLY</p>
      <h2>Who’s coming along?</h2>
      <p className="muted">
        Calendar responses and Go-classified replies retain their source.
        Ambiguous or conflicting replies need organizer review.
      </p>
      <div className="metric-grid">
        {["attending", "maybe", "not_attending", "needs_review"].map(
          (state) => (
            <article key={state}>
              <strong>
                {
                  record.rsvps.filter(
                    (r) =>
                      r.status === state ||
                      (state === "needs_review" && r.conflict),
                  ).length
                }
              </strong>
              <span>{friendlyState(state)}</span>
            </article>
          ),
        )}
      </div>
      <div className="table-wrap">
        <table>
          <caption>Invited people and response evidence</caption>
          <thead>
            <tr>
              <th scope="col">Invitee</th>
              <th scope="col">Response</th>
              <th scope="col">Source / revision</th>
            </tr>
          </thead>
          <tbody>
            {record.event.invitees.map((invitee) => {
              const observations = record.rsvps.filter(
                (r) => r.invitee_id === invitee.id,
              );
              return (
                <tr key={invitee.id}>
                  <td>{invitee.email}</td>
                  <td>
                    {observations.length
                      ? observations.map((r, i) => (
                          <div key={i}>
                            <Badge
                              tone={
                                r.conflict || r.status === "needs_review"
                                  ? "warning"
                                  : ""
                              }
                            >
                              {r.conflict
                                ? "Conflict · needs review"
                                : friendlyState(r.status)}
                            </Badge>
                          </div>
                        ))
                      : "No response"}
                  </td>
                  <td>
                    {observations.map((r, i) => (
                      <div className="small" key={i}>
                        {r.source} · r{r.event_revision}
                        <br />
                        {r.source_id}
                        <br />
                        Observed: {new Date(r.observed_at).toLocaleString()}
                      </div>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {record.event.invitees.length === 0 && (
          <p className="empty">No invitees yet. Add them in event details.</p>
        )}
      </div>
      <p className="notice">
        Private dietary and accessibility details are excluded from invitations
        and shared event material.
      </p>
    </section>
  );
}
function App() {
  const [gateway, setGateway] = useState<EventGateway | null>(null);
  const [session, setSession] = useState<Session>();
  const [page, setPage] = useState<Page>("dashboard");
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [record, setRecord] = useState<WorkspaceEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  const [search, setSearch] = useState("");
  const [backend, setBackend] = useState("Backend not checked");
  const [editorKey, setEditorKey] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const epoch = useRef(0);
  const publishKeys = useRef(new Map<string, string>());
  useEffect(() => {
    heading.current?.focus();
  }, [page, gateway]);
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(
      () => {
        epoch.current++;
        setSession(undefined);
        setGateway(null);
        setRecord(null);
        setEvents([]);
        setBusy(false);
        setLoading(false);
      },
      Math.max(0, session.expires_at - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [session]);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  async function run<T>(action: () => Promise<T>, done: (value: T) => void) {
    const requestEpoch = epoch.current;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const value = await action();
      if (epoch.current === requestEpoch) done(value);
    } catch (err) {
      if (epoch.current === requestEpoch) {
        if (err instanceof ApiError && err.code === "unauthenticated") {
          setSession(undefined);
          setGateway(null);
          setRecord(null);
          setEvents([]);
        }
        setError(
          err instanceof Error ? err.message : "Request failed. Try again.",
        );
      }
    } finally {
      if (epoch.current === requestEpoch) {
        setBusy(false);
        setLoading(false);
      }
    }
  }
  function canLeave() {
    return (
      !dirty || window.confirm("Leave this screen and discard unsaved changes?")
    );
  }
  function navigate(next: Page) {
    if (canLeave()) {
      setPage(next);
      setDirty(false);
      setError("");
      setMessage("");
      setEditorKey((k) => k + 1);
    }
  }
  function enter(api: EventGateway, nextSession?: Session) {
    epoch.current++;
    setGateway(api);
    setSession(nextSession);
    setPage("dashboard");
    setLoading(true);
    void run(() => api.list(), setEvents);
  }
  function openEvent(event: EventRecord) {
    if (!gateway || !canLeave()) return;
    setLoading(true);
    void run(
      () => gateway.get(event.id),
      (value) => {
        setRecord(value);
        setPage("details");
        setDirty(false);
        setEditorKey((k) => k + 1);
      },
    );
  }
  function update(value: WorkspaceEvent) {
    setRecord(value);
    setEvents((all) => [
      ...all.filter((e) => e.id !== value.event.id),
      value.event,
    ]);
    setDirty(false);
    setEditorKey((k) => k + 1);
  }
  function refresh() {
    if (!gateway || !canLeave()) return;
    setLoading(true);
    void run(
      async () => ({
        events: await gateway.list(),
        record: record ? await gateway.get(record.event.id) : null,
      }),
      (value) => {
        setEvents(value.events);
        setRecord(value.record);
        setDirty(false);
        setEditorKey((k) => k + 1);
        setMessage("Latest available state loaded.");
      },
    );
  }
  async function checkBackend() {
    setBackend("Checking backend…");
    try {
      const status = await loadProjectStatus(AbortSignal.timeout(8000));
      setBackend(
        `Backend online · MCP ${status.superhuman.configured ? "configured" : "not configured"} · Go unverified`,
      );
    } catch {
      setBackend("Backend unavailable · retry connection");
    }
  }
  if (!gateway) return <Login onEnter={enter} />;
  const preview = gateway.mode === "preview";
  const title =
    page === "dashboard"
      ? "A little planning. A great gathering."
      : page === "details"
        ? (record?.event.title ?? "Create an event")
        : (pages.find((p) => p.id === page)?.name ?? "");
  const filtered = events.filter((event) =>
    `${event.title} ${event.location}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <aside className="sidebar">
        <a
          className="wordmark"
          href="#main"
          onClick={(e) => {
            e.preventDefault();
            navigate("dashboard");
          }}
        >
          <span className="brand-icon" aria-hidden="true">
            ↗
          </span>
          <span>
            EVENT
            <br />
            <b>WORKSPACE</b>
          </span>
        </a>
        <div className="workspace-label">
          <span className="avatar">O</span>
          <div>
            Organizer workspace
            <small>{preview ? "Local preview" : session?.email}</small>
          </div>
        </div>
        <p className="nav-label">YOUR WORKSPACE</p>
        <nav aria-label="Workspace">
          {pages.map((p) => (
            <button
              key={p.id}
              disabled={
                busy || (p.id !== "dashboard" && p.id !== "details" && !record)
              }
              className={page === p.id ? "active" : ""}
              aria-current={page === p.id ? "page" : undefined}
              onClick={() => navigate(p.id)}
            >
              <span aria-hidden="true">{p.icon}</span>
              {p.name}
              {p.id === "rsvps" &&
                record?.rsvps.some(
                  (r) => r.status === "needs_review" || r.conflict,
                ) && <span className="nav-count">!</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="go-note">
            <span aria-hidden="true">✳</span>
            <strong>Better together, with Go.</strong>
            <p>Start in Superhuman Go. Review and organize here.</p>
          </div>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => {
              if (canLeave()) {
                epoch.current++;
                setGateway(null);
                setSession(undefined);
                setRecord(null);
                setEvents([]);
                setDirty(false);
              }
            }}
          >
            ← {preview ? "Leave preview" : "Sign out"}
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>
            Workspace{" "}
            <span className="breadcrumb">
              / {pages.find((p) => p.id === page)?.name}
            </span>
          </span>
          <div className="topbar-actions">
            <button className="text-button" onClick={checkBackend}>
              {backend}
            </button>
            <span className="avatar" aria-label="Organizer">
              O
            </span>
          </div>
        </header>
        <div className={`mode-banner ${preview ? "" : "live"}`}>
          {preview
            ? "LOCAL PREVIEW · Synthetic sample writing and receipts. Changes stay in memory. No live Go, Canva, Gmail, or Calendar activity."
            : "LIVE API · Actions use your signed-in session. Provider success requires a current receipt."}
        </div>
        <main id="main">
          <div className="page-heading">
            <div>
              <p className="eyebrow">
                {page === "dashboard"
                  ? "BRING PEOPLE TOGETHER"
                  : `EVENT WORKSPACE ${record ? ` / REVISION ${record.event.revision}` : ""}`}
              </p>
              <h1 tabIndex={-1} ref={heading}>
                {title}
              </h1>
              <p className="muted">
                {page === "dashboard"
                  ? "Go gets the plan started. You make it happen."
                  : record
                    ? `${eventDate(record.event.starts_at, record.event.timezone)} · ${record.event.location}`
                    : "Start manually, then let Go help with the writing."}
              </p>
            </div>
            <button className="secondary" disabled={busy} onClick={refresh}>
              ↻ Refresh {record ? "event" : "events"}
            </button>
          </div>
          {error && (
            <div role="alert" className="error-box">
              {error}
              <button className="text-button" onClick={refresh} disabled={busy}>
                Reload current state
              </button>
            </div>
          )}
          <p className="status-message" role="status" aria-live="polite">
            {busy
              ? loading
                ? "Loading current event state…"
                : "Saving your request…"
              : message}
          </p>
          {page === "dashboard" && (
            <>
              <section className="dashboard-hero">
                <div>
                  <Badge>✳ SUPERHUMAN GO + YOUR WORKSPACE</Badge>
                  <h2>
                    Start with an idea.
                    <br />
                    <em>Let Go bring the plan.</em>
                  </h2>
                  <p>
                    Ask Go to create an event through our MCP tools. It appears
                    here for you to edit, review, and bring to life.
                  </p>
                  <div className="prompt-example">
                    <span aria-hidden="true">↗</span>
                    <p>
                      “Create a neighborhood gathering next Saturday. Help me
                      prepare a clear invitation and a flyer.”
                    </p>
                    <span className="small">Example prompt · use in Go</span>
                  </div>
                  <p className="small">
                    MCP event creation is awaiting a connected event tool. This
                    example does not contact Go.
                  </p>
                </div>
                <div className="hero-art" aria-hidden="true">
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                  <div className="art-star">✳</div>
                  <div className="floating-note">
                    THE NEXT
                    <br />
                    <strong>good thing.</strong>
                    <span>Starts with people.</span>
                  </div>
                  <span className="art-spark">✦</span>
                </div>
              </section>
              <section className="metric-grid dashboard-metrics">
                <article>
                  <strong>{events.length.toString().padStart(2, "0")}</strong>
                  <span>Events in your workspace</span>
                </article>
                <article>
                  <strong>
                    {events
                      .filter((e) => e.created_via === "superhuman_go")
                      .length.toString()
                      .padStart(2, "0")}
                  </strong>
                  <span>Started through Go {preview && "· sample"}</span>
                </article>
                <article>
                  <strong>
                    {events
                      .filter((e) => e.status === "draft")
                      .length.toString()
                      .padStart(2, "0")}
                  </strong>
                  <span>Drafts to shape & review</span>
                </article>
              </section>
              <section className="panel event-list">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">YOUR GATHERINGS</p>
                    <h2>On the horizon.</h2>
                  </div>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => {
                      if (canLeave()) {
                        setRecord(null);
                        setPage("details");
                        setDirty(false);
                        setEditorKey((k) => k + 1);
                      }
                    }}
                  >
                    + Create manually
                  </button>
                </div>
                <label className="search">
                  <span>Find an event</span>
                  <input
                    type="search"
                    placeholder="Search events or locations…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
                {filtered.map((event) => (
                  <button
                    className="event-row"
                    key={event.id}
                    disabled={busy}
                    onClick={() => openEvent(event)}
                  >
                    <span className="date-tile">
                      <small>
                        {new Intl.DateTimeFormat("en", {
                          timeZone: event.timezone,
                          month: "short",
                        }).format(new Date(event.starts_at))}
                      </small>
                      <strong>
                        {new Intl.DateTimeFormat("en", {
                          timeZone: event.timezone,
                          day: "numeric",
                        }).format(new Date(event.starts_at))}
                      </strong>
                    </span>
                    <span className="event-summary">
                      <strong>{event.title}</strong>
                      <span>{event.location}</span>
                      <small>
                        {eventDate(event.starts_at, event.timezone)}
                      </small>
                    </span>
                    <span className="event-meta">
                      <Badge>
                        {event.created_via === "superhuman_go"
                          ? "✳ Started in Go"
                          : "Created manually"}
                      </Badge>
                      <span className="small muted">
                        {event.status} · revision {event.revision}
                      </span>
                    </span>
                    <span aria-hidden="true">↗</span>
                  </button>
                ))}
                {filtered.length === 0 && !loading && (
                  <div className="empty">
                    <h3>
                      {search
                        ? "No matching events"
                        : "Your next gathering starts here."}
                    </h3>
                    <p>
                      {search
                        ? "Try another search."
                        : "Create an event manually, or ask Go once the MCP connection is available."}
                    </p>
                  </div>
                )}
              </section>
            </>
          )}
          {page === "details" && (
            <Details
              key={editorKey}
              record={record}
              busy={busy}
              onDirty={() => setDirty(true)}
              onSave={(input) =>
                void run(
                  () =>
                    gateway.save(
                      record?.event.id ?? null,
                      input,
                      record?.event.revision,
                    ),
                  (value) => {
                    update(value);
                    setPage("review");
                    setMessage(
                      preview
                        ? "Saved in this tab only."
                        : "Event revision saved.",
                    );
                  },
                )
              }
            />
          )}
          {record && page === "review" && (
            <Review
              key={editorKey}
              record={record}
              busy={busy}
              onDirty={() => setDirty(true)}
              onPrepare={() => {
                if (canLeave())
                  void run(
                    () =>
                      gateway.prepare(record.event.id, record.event.revision),
                    (value) => {
                      update(value);
                      setMessage(
                        "Awaiting Go. Ask your Go agent to process the event work; the website has not triggered generation.",
                      );
                    },
                  );
              }}
              onReview={(content, facts) =>
                void run(
                  () =>
                    gateway.review(
                      record.event.id,
                      record.event.revision,
                      content,
                      facts,
                    ),
                  (value) => {
                    update(value);
                    setPage("distribution");
                    setMessage("Review saved for this revision.");
                  },
                )
              }
            />
          )}
          {record && page === "distribution" && (
            <Distribution
              key={editorKey}
              record={record}
              preview={preview}
              busy={busy}
              onPublish={() => {
                const action = record.gmail?.sent ? "update" : "publish";
                const lookup = `${record.event.id}:${record.event.revision}:${action}`;
                const key =
                  publishKeys.current.get(lookup) ?? crypto.randomUUID();
                publishKeys.current.set(lookup, key);
                void run(
                  () =>
                    gateway.publish(
                      record.event.id,
                      record.event.revision,
                      action,
                      key,
                    ),
                  (value) => {
                    update(value);
                    setMessage(
                      "Request recorded. Check provider receipts for completion.",
                    );
                  },
                );
              }}
            />
          )}
          {record && page === "updates" && (
            <>
              <section className="panel">
                <p className="eyebrow">A CHANGE OF PLANS</p>
                <h2>Keep the details current.</h2>
                <p className="muted">
                  Save your changed time or location in event details. A new
                  revision requires fresh Go writing, artifact exports, and
                  organizer review.
                </p>
                <div className="update-steps">
                  <article>
                    <span>01</span>
                    <h3>Revise the plan</h3>
                    <p>
                      Edit time, location, or other details. The saved event is
                      the canonical version.
                    </p>
                  </article>
                  <article>
                    <span>02</span>
                    <h3>Review the changes</h3>
                    <p>
                      Compare the new writing and Canva/document revision before
                      authorizing distribution.
                    </p>
                  </article>
                  <article>
                    <span>03</span>
                    <h3>Update with evidence</h3>
                    <p>
                      Keep the same Calendar event.{" "}
                      {record.gmail?.sent
                        ? "Create a new change-notification draft after the sent invitation."
                        : "Replace the existing unsent Gmail draft."}
                    </p>
                  </article>
                </div>
                <div className="notice">
                  <strong>
                    {record.gmail?.sent
                      ? "Previous invitation sent · new notification required"
                      : record.gmail?.draft_id
                        ? "Unsent draft · update existing draft"
                        : "No Gmail draft recorded"}
                  </strong>
                  <p>
                    Sent email and attached flyer bytes are immutable. A current
                    link and a new notification/export carry the latest details.
                  </p>
                </div>
                <button
                  className="secondary"
                  onClick={() => navigate("details")}
                  disabled={busy}
                >
                  Edit event details ↗
                </button>
              </section>
              <SyncStatus record={record} />
            </>
          )}
          {record && page === "rsvps" && <Rsvps record={record} />}
          <footer>
            <span>Made for the moments that bring us together.</span>
            <span>Superhuman Go · Organizer reviewed</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
export default App;
