import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ApiError,
  loadPublicAuthConfig,
  loadProjectStatus,
  signIn,
  googleSignInUrl,
  completeGoogleSignIn,
} from "./api";
import { createPreviewGateway } from "./preview";
import { contentDefinitions, destinations, routeContent } from "./content";
import { emptyFacts, factLabels, friendlyState, safeUrl } from "./types";
import type {
  Content,
  EventGateway,
  EventInput,
  EventRecord,
  FactKey,
  WorkspaceEvent,
  Session,
} from "./types";
import { eventDate, localTime, toInstant } from "./dates";
import "./App.css";
import { createOrganizerGateway } from "./live";
import { GoConnector } from "./GoConnector";
import { InclusionEditor } from "./InclusionEditor";
import {
  DistributionPreview,
  FlyerApproval,
  ProviderCallbackNotice,
  ConnectedServices,
} from "./ProviderPanels";

type Page = "events" | "settings" | "profile";
type Step = "details" | "review" | "distribution";
const steps: { id: Step; name: string }[] = [
  { id: "details", name: "Event details" },
  { id: "review", name: "Design & inclusion" },
  { id: "distribution", name: "Distribution" },
];
const GO_URL = "https://go.superhuman.com/";
const MCP_URL = safeUrl(import.meta.env.VITE_PUBLIC_MCP_URL);
function GatheringIllustration() {
  return (
    <div className="hero-art" aria-hidden="true">
      <div className="hero-orbit" />
      <div className="hero-calendar">
        <div className="hero-calendar-top">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          >
            <rect x="3" y="5" width="18" height="16" rx="4" />
            <path d="M7 3v5m10-5v5M3 11h18" />
          </svg>
          <span />
        </div>
        <div className="hero-calendar-grid">
          {Array.from({ length: 12 }, (_, i) => (
            <span key={i} />
          ))}
        </div>
      </div>
      <div className="hero-float hero-mail">
        <svg
          viewBox="0 0 32 32"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="4" y="7" width="24" height="18" rx="5" />
          <path d="m5 9 9 8a3 3 0 0 0 4 0l9-8" />
        </svg>
      </div>
      <div className="hero-float hero-people">
        <svg
          viewBox="0 0 32 32"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        >
          <circle cx="13" cy="11" r="4" />
          <path d="M5 26v-3a8 8 0 0 1 16 0v3m1-19a4 4 0 0 1 0 8m3 4a7 7 0 0 1 3 7" />
        </svg>
      </div>
      <svg className="hero-spark" viewBox="0 0 40 40" fill="none">
        <path
          d="M20 4c0 10-6 16-16 16 10 0 16 6 16 16 0-10 6-16 16-16C26 20 20 14 20 4Z"
          fill="currentColor"
          opacity=".55"
        />
      </svg>
    </div>
  );
}
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
function GoHandoff({
  event,
  expanded = false,
}: {
  event?: EventRecord;
  expanded?: boolean;
}) {
  const [copyMessage, setCopyMessage] = useState("");
  const prompt = event
    ? `Use the Event Workspace connector to read event ${event.id} (${event.title}), revision ${event.revision}. Update its Canva flyer, event document, plain-language summary, and invitation in the website. Check holiday conflicts, dietary options, and accessibility, keeping unknown facts unknown. Save previews for my review. Do not send invitations until I approve distribution in the website.`
    : "Use the Event Workspace connector to create my event, then prepare its Canva flyer, event document, and invitation. Check inclusion and save everything to the website for my review. Do not send until I approve distribution.";
  async function copy(value: string) {
    try {
      if (!navigator.clipboard) throw new Error();
      await navigator.clipboard.writeText(value);
      setCopyMessage("Copied. Paste it in Superhuman Go.");
    } catch {
      setCopyMessage("Select the text below and copy it to Superhuman Go.");
    }
  }
  return (
    <section className="go-handoff" aria-label="Superhuman Go connection">
      <div className="go-handoff-top">
        <div>
          <span className="eyebrow">SUPERHUMAN GO</span>
          <h2>
            {event ? "Let Go take it from here." : "Plan in Go. See it here."}
          </h2>
          <p>
            Describe the whole event in your own words in Go—details, design,
            guests, and invitations. Go saves each part into its place here.
          </p>
        </div>
        <a className="primary" href={GO_URL} target="_blank" rel="noreferrer">
          Continue in Superhuman Go ↗
        </a>
      </div>
      <details open={expanded || undefined}>
        <summary>Connect the custom MCP & get your prompt</summary>
        <ol className="setup-steps">
          <li>
            <strong>Open Superhuman Go.</strong> Go to Connectors and add the
            Event Workspace custom MCP connector provided by your team.
          </li>
          <li>
            <strong>Connect this website.</strong> Use its hosted MCP address
            and sign in with your organizer account.{" "}
            {MCP_URL ? (
              <>
                <label>
                  Website MCP address
                  <input
                    readOnly
                    value={MCP_URL}
                    onFocus={(e) => e.currentTarget.select()}
                  />
                </label>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => copy(MCP_URL)}
                >
                  Copy MCP address
                </button>
              </>
            ) : (
              <p className="connection-note">
                The hosted MCP address is awaiting setup. Your team needs to
                configure it before Go can write to this workspace.
              </p>
            )}
          </li>
          <li>
            <strong>Describe what you want.</strong> Use any order or wording in
            Go. Ask it to save event details, design instructions, and writing
            through the connector. If something is unclear, Go should ask you
            rather than guess. Return here to review the results.
            <label>
              Prompt for Go
              <textarea
                readOnly
                rows={5}
                value={prompt}
                onFocus={(e) => e.currentTarget.select()}
              />
            </label>
            <button
              type="button"
              className="secondary"
              onClick={() => copy(prompt)}
            >
              Copy prompt
            </button>
          </li>
        </ol>
        <p className="small muted">
          Opening Go does not install the connector or send this prompt
          automatically. Connection has not been verified.{" "}
          <a
            href="https://support.grammarly.com/hc/en-us/articles/40642362241293-About-Superhuman-Go-agents-and-connectors"
            target="_blank"
            rel="noreferrer"
          >
            Connector help ↗
          </a>
        </p>
        <p className="small" role="status">
          {copyMessage}
        </p>
      </details>
    </section>
  );
}
function TransferConnection({
  onConnected,
}: {
  onConnected: (gateway: EventGateway, session: Session) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [config, setConfig] =
    useState<Awaited<ReturnType<typeof loadPublicAuthConfig>>>();
  async function check() {
    setBusy(true);
    setError("");
    try {
      setConfig(await loadPublicAuthConfig());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to check the event API.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function google() {
    if (!config) return;
    setBusy(true);
    setError("");
    try {
      window.location.assign(await googleSignInUrl(config));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to start Google sign-in.",
      );
      setBusy(false);
    }
  }
  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      const session = await signIn(
        String(data.get("email")),
        String(data.get("password")),
        config,
      );
      const gateway = createOrganizerGateway(session.access_token);
      await gateway.list();
      form.reset();
      onConnected(gateway, session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>Test Go → website.</h2>
      <p className="muted">
        Once the backend and Go connector are hosted, connect an existing
        organizer account here to edit events, review Go’s material, and
        authorize distribution. Go executes approved provider work.
      </p>
      <ol className="setup-steps">
        <li>Connect Go to the public HTTPS MCP endpoint.</li>
        <li>
          Ask Go to create a uniquely named test event and return its saved
          event ID.
        </li>
        <li>
          Connect the same organizer account below, then refresh Your events and
          compare the saved details.
        </li>
      </ol>
      {!config && (
        <button className="secondary" disabled={busy} onClick={check}>
          {busy ? "Checking…" : "Check event API"}
        </button>
      )}
      {error && (
        <p role="alert" className="error-box">
          {error}
        </p>
      )}
      {config && (
        <button className="primary" disabled={busy} onClick={google}>
          {busy ? "Connecting…" : "Sign in with Google"}
        </button>
      )}
      {config && (
        <details>
          <summary>Use email and password instead</summary>
          <form onSubmit={connect} className="profile-form">
            <fieldset disabled={busy}>
              <label>
                Organizer account email
                <input
                  name="email"
                  type="email"
                  autoComplete="username"
                  required
                />
              </label>
              <label>
                Account password
                <input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </label>
            </fieldset>
            <button className="secondary" disabled={busy}>
              {busy ? "Connecting…" : "Connect existing workspace"}
            </button>
          </form>
        </details>
      )}
      <p className="small muted">
        Google sign-in creates your organizer account on first use. Session
        access stays in this tab and expires automatically. A connected event
        list alone does not prove a Go write; compare it with Go’s saved ID.
      </p>
    </section>
  );
}
function Details({
  record,
  onSave,
  busy,
  onDirty,
  readOnly = false,
}: {
  record: WorkspaceEvent | null;
  onSave: (input: EventInput) => void;
  busy: boolean;
  onDirty: () => void;
  readOnly?: boolean;
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
          display_name: event?.invitees.find((person) => person.email === email)
            ?.display_name,
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
          <h2>{event ? "Event details" : "Add the basics."}</h2>
        </div>
        {event && <Badge>Revision {event.revision}</Badge>}
      </div>
      <p className="muted">
        Name your event, set the place and time, and add your guests.
      </p>
      {event && (
        <p className="small muted">
          Saved event ID: <code>{event.id}</code>
        </p>
      )}
      <fieldset disabled={busy || readOnly}>
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
          Start and end times use this timezone.
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
          Save your details, then prepare the design and inclusion review.
        </p>
        <button className="primary" disabled={busy || readOnly}>
          {readOnly ? "Read-only event" : busy ? "Saving…" : "Save & continue"}
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
  onContinue,
  inclusionElsewhere = false,
}: {
  inclusionElsewhere?: boolean;
  record: WorkspaceEvent;
  busy: boolean;
  onPrepare: () => void;
  onReview: (content: Content[], facts: WorkspaceEvent["facts"]) => void;
  onDirty: () => void;
  onContinue: () => void;
}) {
  const [content, setContent] = useState(record.content);
  const [facts, setFacts] = useState(record.facts ?? emptyFacts());
  const [ack, setAck] = useState(false);
  const [error, setError] = useState("");
  const groupedContent = routeContent(content);
  const current = content.filter(
    (c) => c.event_revision === record.event.revision,
  );
  function save(e: FormEvent) {
    e.preventDefault();
    setError("");
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
    if (current.some((c) => !c.body.trim())) {
      setError("Writing previews cannot be empty.");
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
  function fact(key: FactKey) {
    const label = factLabels[key];
    return (
      <fieldset
        className="fact"
        key={key}
        disabled={busy || record.live?.factsReadOnly}
      >
        <legend>{label}</legend>
        <label>
          What do you know?
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
            <option value="yes">Yes · confirmed</option>
            <option value="no">No · confirmed</option>
          </select>
        </label>
        <label>
          {key === "observances"
            ? "Which holidays or observances should Go check?"
            : key === "diet"
              ? "Is food served? Which dietary options are confirmed?"
              : "Notes"}
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
        <details>
          <summary>Source & confirmation date</summary>
          <label>
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
          <label>
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
        </details>
      </fieldset>
    );
  }
  return (
    <>
      <GoHandoff event={record.event} />
      <form onSubmit={save} onChange={onDirty}>
        <section className="panel">
          <div className="section-heading">
            <h2>Design your event.</h2>
            <a
              className="secondary"
              href={GO_URL}
              target="_blank"
              rel="noreferrer"
            >
              Connect Canva in Go ↗
            </a>
          </div>
          <p className="muted">
            Ask Go to create or update your Canva flyer and event document, then
            review them here.
          </p>
          <div className="asset-grid">
            {(["flyer", "document"] as const).map((kind) => {
              const asset =
                record.assets.find(
                  (a) =>
                    a.kind === kind &&
                    a.event_revision === record.event.revision,
                ) ??
                record.assets
                  .filter((a) => a.kind === kind)
                  .sort((a, b) => b.event_revision - a.event_revision)[0];
              return (
                <article className="asset" key={kind}>
                  <div className="asset-preview">
                    {kind === "flyer" && safeUrl(asset?.preview_url) ? (
                      <img
                        src={safeUrl(asset?.preview_url)}
                        alt={
                          asset?.alt_text ||
                          "Flyer preview awaiting accessible text"
                        }
                      />
                    ) : (
                      <span aria-hidden="true">
                        {kind === "flyer" ? "◇" : "≡"}
                      </span>
                    )}
                  </div>
                  <h3>{kind === "flyer" ? "Canva flyer" : "Event document"}</h3>
                  <p className="small muted">
                    {asset
                      ? `Revision ${asset.event_revision} · ${asset.event_revision === record.event.revision ? friendlyState(asset.state) : "stale"}`
                      : "Waiting for Go to save an artifact."}
                  </p>
                  <ExternalLink url={asset?.edit_url}>
                    Edit in Canva
                  </ExternalLink>
                  <ExternalLink url={asset?.current_url}>
                    Open current {kind}
                  </ExternalLink>
                </article>
              );
            })}
          </div>
        </section>
        <section className="panel" hidden={inclusionElsewhere}>
          <h2>A quick inclusion check.</h2>
          {record.live?.factsReadOnly && (
            <p className="notice">
              Server inclusion facts are read-only until the inclusion save API
              is connected. Unknown remains unknown; reviewing writing does not
              certify venue access or dietary accommodations.
            </p>
          )}
          <p className="muted">
            Check holidays and food options before you send. Leave unconfirmed
            details unknown.
          </p>
          <div className="fact-grid">
            {fact("observances")}
            {fact("diet")}
          </div>
          <details className="more-details">
            <summary>Access, captions & sensory details</summary>
            <div className="fact-grid">
              {(
                [
                  "step_free",
                  "elevator",
                  "captions",
                  "loud_sound",
                  "strobes",
                ] as FactKey[]
              ).map(fact)}
            </div>
          </details>
          {record.findings.map((f, i) => (
            <article className="finding" key={i}>
              <Badge>{friendlyState(f.status)}</Badge>{" "}
              <strong>{f.category}</strong>
              <p>{friendlyState(f.reason)}</p>
              {f.sources.map((source, n) => (
                <p className="small" key={n}>
                  {source.reference} · {source.checked_on}
                </p>
              ))}
            </article>
          ))}
          <p className="small muted">
            This review does not certify the venue. Private guest needs stay out
            of shared invitations.
          </p>
        </section>
        <section className="panel">
          <div className="section-heading">
            <h2>Review Go’s writing.</h2>
            <button
              type="button"
              className="text-button"
              disabled={busy}
              onClick={onPrepare}
            >
              Queue preparation
            </button>
          </div>
          {record.work.map((work) => (
            <p className="small queue-state" key={work.id}>
              <Badge>
                {work.event_revision === record.event.revision
                  ? friendlyState(work.state)
                  : "stale"}
              </Badge>{" "}
              Revision {work.event_revision}
            </p>
          ))}
          {!current.length && (
            <p className="notice">
              Waiting for Go’s first draft. Open Go and use the event prompt
              above.
            </p>
          )}
          {destinations.map(
            (destination) =>
              groupedContent[destination.id].length > 0 && (
                <div
                  key={destination.id}
                  className="content-group"
                  role="group"
                  aria-label={`Go output: ${destination.label}`}
                >
                  <h3>{destination.label}</h3>
                  {groupedContent[destination.id].map((c) => (
                    <details className="writing-preview" key={c.id}>
                      <summary>
                        {contentDefinitions[c.kind].label}{" "}
                        <Badge
                          tone={
                            c.event_revision !== record.event.revision
                              ? "warning"
                              : ""
                          }
                        >
                          {c.event_revision === record.event.revision
                            ? friendlyState(c.state)
                            : `Stale · r${c.event_revision}`}
                        </Badge>
                      </summary>
                      {(c.kind === "invitation" ||
                        c.kind === "change_notice") && (
                        <label>
                          Email subject
                          <input
                            value={c.subject ?? ""}
                            disabled={
                              busy || c.event_revision !== record.event.revision
                            }
                            onChange={(e) =>
                              setContent((all) =>
                                all.map((item) =>
                                  item.id === c.id
                                    ? {
                                        ...item,
                                        subject: e.target.value,
                                        producer: "organizer",
                                        state: "needs_review",
                                      }
                                    : item,
                                ),
                              )
                            }
                          />
                        </label>
                      )}
                      <label>
                        {contentDefinitions[c.kind].label}
                        <span className="small muted">
                          {c.producer === "superhuman_go"
                            ? "Superhuman Go"
                            : "Edited by organizer"}{" "}
                          · revision {c.event_revision}
                        </span>
                        <textarea
                          rows={5}
                          value={c.body}
                          disabled={
                            busy || c.event_revision !== record.event.revision
                          }
                          onChange={(e) =>
                            setContent((all) =>
                              all.map((item) =>
                                item.id === c.id
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
                    </details>
                  ))}
                </div>
              ),
          )}
          <label className="checkbox">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />
            I reviewed this revision’s writing, design, and inclusion questions,
            including unknowns.
          </label>
          {record?.live?.warnings.map((warning) => (
            <p className="notice" key={warning}>
              {warning}
            </p>
          ))}
          {error && (
            <p role="alert" className="error-box">
              {error}
            </p>
          )}
          <div className="action-row">
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={onContinue}
            >
              Preview distribution
            </button>
            <button
              className="primary"
              disabled={
                busy ||
                !ack ||
                !current.length ||
                record.live?.reviewAvailable === false
              }
            >
              Save review & continue
            </button>
          </div>
        </section>
      </form>
    </>
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
  onPublish: (action: "publish" | "update") => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [action, setAction] = useState<"publish" | "update" | null>(
    record.gmail?.sent ? "update" : record.live ? null : "publish",
  );
  const sent = action === "update";
  const approval = record.live?.approval;
  const executed = Boolean(
    approval &&
    record.operations.some(
      (op) =>
        op.approval_id === approval.id &&
        op.event_revision === approval.event_revision &&
        op.kind === "gmail_send" &&
        op.state === "succeeded",
    ),
  );
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
        ["ready", "succeeded"].includes(a.state) &&
        (!record.live || Boolean(a.current_url)),
    ),
  );
  const reviewed =
    record.review_revision === record.event.revision && !!mail && readyAssets;
  return (
    <>
      {approval && (
        <section className="panel">
          <h2>
            {executed
              ? "Gmail send confirmed by provider receipt."
              : "Approval recorded. Awaiting Go."}
          </h2>
          <p>
            {executed
              ? "The reviewed message was sent. Delivered email and attachments are immutable snapshots."
              : "This approval does not prove an invitation was sent. Ask Go to execute it, then refresh provider receipts."}
          </p>
          {!executed && (
            <label>
              Approved distribution prompt
              <textarea
                readOnly
                rows={4}
                value={`For event ${record.event.id}, revision ${approval.event_revision}, preview distribution and execute_distribution using approval_id ${approval.id}. Use only this approved revision. Reconcile existing provider state; do not create duplicate invitations. Report receipts or blockers.`}
              />
            </label>
          )}
        </section>
      )}
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
              <strong>{mail?.subject || record.event.title}</strong>
            </div>
            <div className="mail-body">
              {mail?.body ??
                `Awaiting reviewed ${sent ? "change notice" : "invitation"} for revision ${record.event.revision}.`}
            </div>
            <div className="mail-footer">
              Invitations include current event and flyer links. Attached files
              are revision snapshots.
            </div>
          </div>
        </section>
        <section className="panel">
          <p className="eyebrow">PUBLISH CHECKLIST</p>
          <h2>Your call to send.</h2>
          {record.live && !record.gmail?.sent && (
            <fieldset disabled={busy || Boolean(approval)}>
              <legend>Which message are you authorizing?</legend>
              <p className="small muted">
                The API does not expose the Gmail draft binding. Confirm the
                message type; Go must reconcile Gmail before execution.
              </p>
              <label>
                <input
                  type="radio"
                  name="distribution-action"
                  checked={action === "publish"}
                  onChange={() => {
                    setAction("publish");
                    setConfirmed(false);
                  }}
                />{" "}
                First invitation — I confirm none was sent
              </label>
              <label>
                <input
                  type="radio"
                  name="distribution-action"
                  checked={action === "update"}
                  onChange={() => {
                    setAction("update");
                    setConfirmed(false);
                  }}
                />{" "}
                Change notice — an invitation was already sent
              </label>
            </fieldset>
          )}
          <ul className="checklist">
            <li>
              {record.review_revision === record.event.revision ? "✓" : "○"}{" "}
              {record.live
                ? "Current writing reviewed for"
                : "Writing and inclusion reviewed for"}{" "}
              r{record.event.revision}
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
              : record.live
                ? "This records an approval for Go to execute. Nothing sends until Go calls the approved distribution tool. Review all inclusion unknowns before approving."
                : "This action authorizes Calendar invitations and Gmail delivery for the exact reviewed revision. Partial failures remain visible below."}
          </p>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              disabled={
                preview ||
                !reviewed ||
                busy ||
                !action ||
                Boolean(approval) ||
                record.live?.receiptsAvailable === false
              }
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
              !record.event.invitees.length ||
              !action ||
              Boolean(approval) ||
              record.live?.receiptsAvailable === false
            }
            onClick={() => {
              if (action) onPublish(action);
            }}
          >
            {busy
              ? "Requesting…"
              : approval
                ? "Approval recorded · awaiting Go"
                : record.live
                  ? "Confirm & authorize Go"
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
      <details className="panel">
        <summary>Provider status & revisions</summary>
        <SyncStatus record={record} />
      </details>
    </>
  );
}
function Rsvps({ record }: { record: WorkspaceEvent }) {
  return (
    <section className="panel">
      {record.live?.rsvpsAvailable === false && (
        <p role="status">
          Guest responses are unavailable. No attendance totals are confirmed.
        </p>
      )}
      <p className="eyebrow">PRIVATE / ORGANIZER ONLY</p>
      <h2>Who’s coming along?</h2>
      <p className="muted">
        Calendar responses and Go-classified replies retain their source.
        Ambiguous or conflicting replies need organizer review.
      </p>
      {record.live?.rsvpsAvailable !== false && (
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
      )}
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
                      : record.live?.rsvpsAvailable === false
                        ? "Unavailable"
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
function App({ eventGateway }: { eventGateway?: EventGateway } = {}) {
  // A live gateway must already carry organizer auth; default remains the public local preview.
  const [gateway, setGateway] = useState(
    () => eventGateway ?? createPreviewGateway(),
  );
  const [session, setSession] = useState<Session>();
  const [starting, setStarting] = useState(false);
  const [page, setPage] = useState<Page>("events");
  const [step, setStep] = useState<Step>("details");
  const [editing, setEditing] = useState(false);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [record, setRecord] = useState<WorkspaceEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const [backend, setBackend] = useState("Not checked");
  const [profile, setProfile] = useState({ name: "Organizer", email: "" });
  const heading = useRef<HTMLHeadingElement>(null);
  const publishKeys = useRef(new Map<string, string>());
  const epoch = useRef(0);
  // Provider actions need the organizer's own session on a full (not read-only) live gateway.
  const providerSession =
    gateway.mode === "live" && !gateway.readOnly ? session : undefined;
  const pendingLinkedEvent = useRef(
    new URLSearchParams(location.search).get("event"),
  );
  const openLinkedEvent = useEffectEvent((id: string) => openEvent(id));
  useEffect(() => {
    if (gateway.mode !== "live" || pendingLinkedEvent.current === null) return;
    const id = pendingLinkedEvent.current;
    pendingLinkedEvent.current = null;
    openLinkedEvent(id);
  }, [gateway]);
  const watchedId =
    gateway.mode === "live" && editing ? record?.event.id : undefined;
  const watchPaused = Boolean(gateway.mode === "live" && (busy || dirty));
  useEffect(() => {
    let active = true;
    let inFlight = false;
    async function load() {
      if (inFlight || watchPaused) return;
      inFlight = true;
      try {
        const list = await gateway.list();
        const item = watchedId ? await gateway.get(watchedId) : undefined;
        if (!active) return;
        setEvents(list);
        if (item) {
          setRecord((current) =>
            JSON.stringify(current) === JSON.stringify(item) ? current : item,
          );
        }
        setLoadError("");
      } catch (err) {
        if (!active) return;
        if (err instanceof ApiError && err.code === "unauthenticated") {
          setEvents([]);
          setRecord(null);
          setEditing(false);
        }
        setLoadError(
          err instanceof Error
            ? err.message
            : "Could not load events. Try refreshing.",
        );
      } finally {
        inFlight = false;
      }
    }
    void load();
    if (gateway.mode !== "live")
      return () => {
        active = false;
      };
    const refreshVisible = () => {
      if (document.visibilityState !== "hidden") void load();
    };
    const timer = window.setInterval(refreshVisible, 10000);
    window.addEventListener("focus", refreshVisible);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshVisible);
    };
  }, [gateway, watchedId, watchPaused]);
  useEffect(() => {
    heading.current?.focus();
  }, [page, step, editing, starting]);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(
      () => {
        epoch.current++;
        setBusy(false);
        setEvents([]);
        setGateway(createPreviewGateway());
        setSession(undefined);
        setRecord(null);
        setEditing(false);
        setStarting(false);
        setDirty(false);
        setMessage("The workspace session expired. Reconnect in Settings.");
      },
      Math.max(0, session.expires_at - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [session]);
  function connectWorkspace(next: EventGateway, activeSession: Session) {
    if (!canLeave()) return;
    epoch.current++;
    setEvents([]);
    setBusy(false);
    setGateway(next);
    setSession(activeSession);
    setRecord(null);
    setEditing(false);
    setStarting(false);
    setDirty(false);
    setMessage(
      "Connected to real organizer events. Open Your events to compare Go’s saved ID.",
    );
  }
  const googleSignInResult = useEffectEvent(
    (result: { gateway: EventGateway; session: Session } | Error) => {
      if (!(result instanceof Error))
        return connectWorkspace(result.gateway, result.session);
      setPage("settings");
      setError(result.message);
    },
  );
  useEffect(() => {
    if (eventGateway) return;
    completeGoogleSignIn()
      .then(async (activeSession) => {
        if (!activeSession) return;
        const next = createOrganizerGateway(activeSession.access_token);
        await next.list();
        googleSignInResult({ gateway: next, session: activeSession });
      })
      .catch((err: unknown) =>
        googleSignInResult(
          err instanceof Error
            ? err
            : new Error("Google sign-in did not finish."),
        ),
      );
  }, [eventGateway]);
  async function run<T>(action: () => Promise<T>, done: (value: T) => void) {
    const requestEpoch = epoch.current;
    setBusy(true);
    setError("");
    setLoadError("");
    setMessage("");
    try {
      const result = await action();
      if (requestEpoch === epoch.current) done(result);
    } catch (err) {
      if (requestEpoch === epoch.current)
        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong. Try again.",
        );
    } finally {
      if (requestEpoch === epoch.current) setBusy(false);
    }
  }
  function canLeave() {
    return !dirty || window.confirm("Discard unsaved changes?");
  }
  function navigate(next: Page) {
    if (!canLeave()) return;
    setPage(next);
    setStarting(false);
    setEditing(false);
    setDirty(false);
    setError("");
    setMessage("");
  }
  function changeStep(next: Step) {
    if (!canLeave()) return;
    setStep(next);
    setDirty(false);
    setEditorKey((k) => k + 1);
    setError("");
    setMessage("");
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
    if (!canLeave()) return;
    void run(
      async () => ({
        list: await gateway.list(),
        item: record && editing ? await gateway.get(record.event.id) : null,
      }),
      (value) => {
        setEvents(value.list);
        if (value.item) update(value.item);
        setMessage("Latest available state loaded.");
      },
    );
  }
  function addEvent() {
    if (canLeave()) {
      setRecord(null);
      setStarting(true);
      setEditing(false);
      setStep("details");
      setDirty(false);
      setEditorKey((k) => k + 1);
      setMessage("");
    }
  }
  function openEvent(id: string) {
    void run(
      async () => {
        try {
          return await gateway.get(id);
        } catch (error) {
          if (
            error instanceof ApiError &&
            ["api_unavailable", "forbidden"].includes(error.code)
          ) {
            throw new Error(
              "Event not found. It may not exist or be available to this organizer.",
            );
          }
          throw error;
        }
      },
      (value) => {
        setPage("events");
        setStarting(false);
        setRecord(value);
        setEditing(true);
        setStep("details");
        setEditorKey((k) => k + 1);
      },
    );
  }
  async function checkBackend() {
    setBackend("Checking…");
    try {
      const status = await loadProjectStatus(AbortSignal.timeout(8000));
      setBackend(
        `Backend online · MCP ${status.superhuman.configured ? "configured" : "not configured"} · Go unverified`,
      );
    } catch {
      setBackend("Backend unavailable. Try again.");
    }
  }
  const recordVersion = record
    ? `${record.event.id}:${record.event.revision}:${record.content.map((item) => `${item.id}:${item.state}`).join(",")}:${JSON.stringify(record.facts)}`
    : "new";
  const title =
    page === "settings"
      ? "Settings"
      : page === "profile"
        ? "Profile"
        : starting
          ? "Start your event with Go"
          : editing
            ? (record?.event.title ?? "New event")
            : "Your events";
  useEffect(() => {
    const stage =
      editing && page === "events"
        ? ` · ${steps.find((item) => item.id === step)?.name}`
        : "";
    document.title = `${title}${stage} · Event Workspace · Superhuman Go`;
  }, [title, editing, page, step]);
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
            navigate("events");
          }}
        >
          <span className="brand-icon" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="4" y="5" width="16" height="16" rx="4" />
              <path d="M8 3v5m8-5v5M4 11h16m-12 5 3 2 5-4" />
            </svg>
          </span>
          Event Workspace
        </a>
        <nav aria-label="Workspace">
          {(
            [
              { id: "events", name: "Your events", icon: "▦" },
              { id: "settings", name: "Settings", icon: "⚙" },
              { id: "profile", name: "Profile", icon: "○" },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "active" : ""}
              aria-current={page === item.id ? "page" : undefined}
              disabled={busy}
              onClick={() => navigate(item.id)}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.name}
            </button>
          ))}
        </nav>
        <div className="sidebar-caption">
          <span>POWERED BY SUPERHUMAN GO</span>
          <p>
            A little more clarity.
            <br />A lot more connection.
          </p>
        </div>
        <div className="sidebar-profile">
          <span className="avatar" aria-hidden="true">
            {profile.name.charAt(0).toUpperCase()}
          </span>
          <span>
            {profile.name}
            <small>
              {gateway.mode === "live"
                ? "Connected workspace"
                : "Local workspace"}
            </small>
          </span>
        </div>
      </aside>
      <div className="main-shell">
        <main id="main" tabIndex={-1}>
          <header className="page-heading">
            <div>
              {(editing || starting) && page === "events" && (
                <button
                  className="text-button back-button"
                  disabled={busy}
                  onClick={() => navigate("events")}
                >
                  ← Your events
                </button>
              )}
              <h1
                ref={heading}
                tabIndex={-1}
                aria-describedby={
                  editing && page === "events" ? "page-description" : undefined
                }
              >
                {title}
              </h1>
              <p className="muted" id="page-description">
                {page === "settings"
                  ? "Connect Go to your workspace."
                  : page === "profile"
                    ? "A few details about you."
                    : starting
                      ? "Describe the plan in Go, then review it here."
                      : editing
                        ? `Step ${steps.findIndex((item) => item.id === step) + 1} of 3: ${steps.find((item) => item.id === step)?.name}.`
                        : "All your gatherings, in one place."}
              </p>
            </div>
            {page === "events" && (
              <button className="secondary" disabled={busy} onClick={refresh}>
                ↻ Refresh
              </button>
            )}
          </header>
          {pendingLinkedEvent.current !== null &&
            gateway.mode === "preview" && (
              <section className="notice">
                <p>Connect your organizer account to open the linked event.</p>
                <button
                  className="secondary"
                  onClick={() => navigate("settings")}
                >
                  Connect to open event
                </button>
              </section>
            )}
          <p className="preview-note">
            {gateway.mode === "preview"
              ? "Local preview · sample data · changes stay in this tab · no invitations send"
              : gateway.readOnly
                ? "Connected event-details test · checks every 10 seconds · read-only · materials and distribution are not loaded"
                : "Connected organizer workspace · review changes before sending"}
          </p>
          {(error || loadError) && (
            <p role="alert" className="error-box">
              {error || loadError}
            </p>
          )}
          <ProviderCallbackNotice />
          <p className="status-message" role="status">
            {busy ? "Working…" : message}
          </p>
          {page === "events" && starting && (
            <>
              <GoHandoff expanded />
              <section className="panel">
                <h2>After Go saves your event</h2>
                <p className="muted">
                  Come back to Your events and refresh. Open the saved event and
                  compare its name, location, times, and guest list with your
                  request.
                </p>
                {gateway.mode === "preview" && (
                  <p className="notice">
                    You are viewing local sample data. Go cannot write to this
                    tab. Connect the hosted backend in Settings before testing a
                    real transfer.
                  </p>
                )}
                <div className="action-row">
                  <button
                    className="primary"
                    disabled={busy || gateway.mode === "preview"}
                    onClick={() => {
                      setStarting(false);
                      refresh();
                    }}
                  >
                    Check Your events
                  </button>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => navigate("settings")}
                  >
                    Connection settings
                  </button>
                </div>
              </section>
              <button
                className="text-button"
                disabled={busy || gateway.readOnly}
                onClick={() => {
                  setStarting(false);
                  setEditing(true);
                  setEditorKey((k) => k + 1);
                }}
              >
                Enter event details manually instead
              </button>
            </>
          )}
          {page === "events" && !editing && !starting && (
            <>
              <section
                className="workspace-hero"
                aria-labelledby="gathering-heading"
              >
                <div className="hero-copy">
                  <span className="eyebrow">
                    LESS PLANNING. MORE POSSIBILITY.
                  </span>
                  <h2 id="gathering-heading">
                    Good plans.
                    <br />
                    <span>Great gatherings.</span>
                  </h2>
                  <p>
                    Bring the details together. Let Superhuman Go help with the
                    rest.
                  </p>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={addEvent}
                  >
                    Plan with Superhuman Go <span aria-hidden="true">↗</span>
                  </button>
                </div>
                <GatheringIllustration />
              </section>
              <div className="events-toolbar">
                <h2>
                  Upcoming events <span>{events.length}</span>
                </h2>
                <button
                  className="primary add-event"
                  aria-label="Add event"
                  disabled={busy}
                  onClick={addEvent}
                >
                  <span aria-hidden="true">+</span> New event
                </button>
              </div>
              <div className="events-grid">
                {events.map((event) => (
                  <button
                    className="event-card"
                    key={event.id}
                    disabled={busy}
                    onClick={() => openEvent(event.id)}
                  >
                    <div className="event-card-top">
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
                      <Badge>{friendlyState(event.status)}</Badge>
                    </div>
                    <h3>{event.title}</h3>
                    <p>{event.location}</p>
                    <p className="small">
                      {eventDate(event.starts_at, event.timezone)}
                    </p>
                    <div className="event-card-footer">
                      <span>{event.invitees.length} guests</span>
                      <span>Open event ↗</span>
                    </div>
                  </button>
                ))}
                <button
                  className="add-event-card"
                  disabled={busy}
                  onClick={addEvent}
                >
                  <span aria-hidden="true">+</span>Add a new event
                </button>
              </div>
              <div className="go-shortcut">
                <span aria-hidden="true">✳</span>
                <p>
                  Prefer to plan with Go? Connect this workspace, then prompt Go
                  to create and update your events.
                </p>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => navigate("settings")}
                >
                  Set up Go ↗
                </button>
              </div>
            </>
          )}
          {page === "events" && editing && (
            <>
              <nav className="stepper" aria-label="Event creation">
                {steps.map((item, i) => (
                  <button
                    key={item.id}
                    className={step === item.id ? "active" : ""}
                    aria-current={step === item.id ? "step" : undefined}
                    disabled={
                      busy ||
                      (gateway.readOnly && item.id !== "details") ||
                      (!record && item.id !== "details")
                    }
                    onClick={() => changeStep(item.id)}
                  >
                    <span>{i + 1}</span>
                    {item.name}
                  </button>
                ))}
              </nav>
              {step === "details" && (
                <Details
                  key={`${editorKey}:${recordVersion}`}
                  record={record}
                  busy={busy}
                  readOnly={gateway.readOnly}
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
                        setStep("review");
                        setMessage(
                          "Event saved. Continue in Go to prepare your materials.",
                        );
                      },
                    )
                  }
                />
              )}
              {record && step === "review" && providerSession && (
                <FlyerApproval
                  eventId={record.event.id}
                  revision={record.event.revision}
                  accessToken={providerSession.access_token}
                />
              )}
              {record && step === "review" && providerSession && (
                <InclusionEditor
                  eventId={record.event.id}
                  revision={record.event.revision}
                  accessToken={providerSession.access_token}
                />
              )}
              {record && step === "review" && (
                <Review
                  key={`${editorKey}:${recordVersion}`}
                  inclusionElsewhere={Boolean(providerSession)}
                  record={record}
                  busy={busy}
                  onDirty={() => setDirty(true)}
                  onContinue={() => changeStep("distribution")}
                  onPrepare={() => {
                    if (canLeave())
                      void run(
                        () =>
                          gateway.prepare(
                            record.event.id,
                            record.event.revision,
                          ),
                        (value) => {
                          update(value);
                          setMessage(
                            "Awaiting Go. Open Superhuman Go and ask it to process this event.",
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
                        setStep("distribution");
                        setMessage(
                          value.live
                            ? "Writing review saved for this revision. Inclusion facts remain as reported by the server."
                            : "Review saved for this revision.",
                        );
                      },
                    )
                  }
                />
              )}
              {record && step === "distribution" && (
                <>
                  <div className="distribution-go">
                    <p>
                      Ask Go to prepare emails, personalized invitations, and
                      Calendar updates. Review the results here before sending.
                    </p>
                    <a
                      className="secondary"
                      href={GO_URL}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open Superhuman Go ↗
                    </a>
                  </div>
                  {providerSession && (
                    <DistributionPreview
                      eventId={record.event.id}
                      revision={record.event.revision}
                      accessToken={providerSession.access_token}
                    />
                  )}
                  <Distribution
                    key={`${editorKey}:${recordVersion}`}
                    record={record}
                    preview={gateway.mode === "preview"}
                    busy={busy}
                    onPublish={(action) => {
                      const keyId = `${record.event.id}:${record.event.revision}:${action}`;
                      const key =
                        publishKeys.current.get(keyId) ?? crypto.randomUUID();
                      publishKeys.current.set(keyId, key);
                      void run(
                        () =>
                          gateway.publish(
                            record.event.id,
                            record.event.revision,
                            action,
                            key,
                            record.content.find(
                              (item) =>
                                item.kind ===
                                  (action === "update"
                                    ? "change_notice"
                                    : "invitation") &&
                                item.event_revision === record.event.revision &&
                                item.state === "ready",
                            )?.id,
                          ),
                        (value) => {
                          update(value);
                          setMessage(
                            value.live?.approval
                              ? "Approval recorded. Awaiting Go. Check provider receipts for completion."
                              : "Request recorded. Check provider receipts for completion.",
                          );
                        },
                      );
                    }}
                  />
                  <details className="panel">
                    <summary>Guest responses</summary>
                    <Rsvps record={record} />
                  </details>
                </>
              )}
            </>
          )}
          {page === "settings" && (
            <>
              <GoHandoff expanded />
              {gateway.mode === "preview" ? (
                <TransferConnection onConnected={connectWorkspace} />
              ) : (
                <section className="panel">
                  <h2>Workspace connected</h2>
                  <p className="muted">
                    {session?.email ?? "Authenticated organizer gateway"} ·
                    organizer workspace
                  </p>
                  <button
                    className="secondary"
                    onClick={() => {
                      if (canLeave()) {
                        epoch.current++;
                        setEvents([]);
                        setBusy(false);
                        setSession(undefined);
                        setGateway(createPreviewGateway());
                        setRecord(null);
                        setDirty(false);
                      }
                    }}
                  >
                    Disconnect workspace
                  </button>
                </section>
              )}
              {session && (
                <GoConnector
                  key={`${session.email}:${session.expires_at}`}
                  accessToken={session.access_token}
                />
              )}
              <ConnectedServices
                key={providerSession?.expires_at ?? "signed-out"}
                accessToken={providerSession?.access_token}
              />
              <details className="panel">
                <summary>Workspace connection status</summary>
                <p className="small muted">{backend}</p>
                <button className="secondary" onClick={checkBackend}>
                  Check connection
                </button>
              </details>
            </>
          )}
          {page === "profile" && (
            <form
              className="panel profile-form"
              onChange={() => setDirty(true)}
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                setProfile({
                  name: String(data.get("name")).trim(),
                  email: String(data.get("email")).trim(),
                });
                setDirty(false);
                setMessage("Profile saved in this tab.");
              }}
            >
              <label>
                Your name
                <input
                  name="name"
                  required
                  maxLength={100}
                  defaultValue={profile.name}
                />
              </label>
              <label>
                Email <span className="optional">optional</span>
                <input name="email" type="email" defaultValue={profile.email} />
              </label>
              <p className="small muted">
                These details stay in this tab. Account sign-in is skipped for
                now.
              </p>
              <button className="primary">Save profile</button>
            </form>
          )}
        </main>
      </div>
    </div>
  );
}
export default App;
