import { useEffect, useState } from "react";
import {
  abandonFlyer,
  approveFlyer,
  loadAssetStatus,
  loadConnection,
  loadDistributionPlan,
  ProviderRequestError,
  providerNames,
  readCallback,
  startConnection,
} from "./providers";
import type {
  AssetStatus,
  CallbackResult,
  Connection,
  DistributionPlan,
  FlyerView,
  Provider,
} from "./providers";

const failure = (err: unknown, fallback: string) =>
  err instanceof Error ? err.message : fallback;

/** Shows the OAuth callback result once, then removes the flag (keeps ?event= and the rest). */
export function ProviderCallbackNotice() {
  const [result, setResult] = useState<CallbackResult | null>(
    () => readCallback(window.location.href).result,
  );
  useEffect(() => {
    const { result, cleaned } = readCallback(window.location.href);
    if (result) window.history.replaceState(window.history.state, "", cleaned);
  }, []);
  if (!result) return null;
  return (
    <section className={result.ok ? "notice" : "notice error-box"}>
      <p role={result.ok ? "status" : "alert"}>{result.message}</p>
      <button className="secondary" onClick={() => setResult(null)}>
        Dismiss {providerNames[result.provider]} message
      </button>
    </section>
  );
}

const providerScope: Record<Provider, string> = {
  google: "Calendar invitations and Gmail drafts are sent from this account.",
  canva: "Go creates and exports your flyer in this Canva account.",
};

export function ProviderConnection({
  provider,
  accessToken,
  navigate = (url) => window.location.assign(url),
}: {
  provider: Provider;
  accessToken: string;
  navigate?: (url: string) => void;
}) {
  const name = providerNames[provider];
  const [status, setStatus] = useState<Connection | "loading" | "error">(
    "loading",
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    loadConnection(provider, accessToken).then(
      (value) => active && setStatus(value),
      (err) => {
        if (!active) return;
        setStatus("error");
        setError(failure(err, `${name} status is unavailable.`));
      },
    );
    return () => {
      active = false;
    };
  }, [provider, accessToken, name]);
  const connected = typeof status === "object" && status.connected;
  return (
    <section className="panel" aria-labelledby={`${provider}-connection`}>
      <h2 id={`${provider}-connection`}>{name} account</h2>
      <p className="muted">{providerScope[provider]}</p>
      <p role="status">
        {status === "loading"
          ? `Checking ${name} connection…`
          : status === "error"
            ? `${name} connection status unknown.`
            : status.connected
              ? `Connected${status.email ? ` as ${status.email}` : ""}.`
              : "Not connected."}
        {message && ` ${message}`}
      </p>
      <button
        className="secondary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            const url = await startConnection(provider, accessToken);
            setMessage(`Opening ${name}…`);
            navigate(url);
          } catch (err) {
            setError(failure(err, `Could not start the ${name} connection.`));
            setBusy(false);
          }
        }}
      >
        {connected ? `Reconnect ${name}` : `Connect ${name}`}
      </button>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

const stageText: Record<string, string> = {
  creating: "Go is creating the flyer in Canva.",
  pending: "Canva is still creating the flyer. Ask Go to check it again.",
  created: "The flyer exists. Ask Go to prepare a preview for your approval.",
  previewed:
    "Check this preview. Go cannot export the flyer until you approve it.",
  approved: "You approved this preview. Ask Go to export the flyer.",
  exporting: "Canva is exporting the approved flyer.",
  stored: "The approved flyer is exported and stored for this revision.",
  failed: "The flyer could not be prepared. Ask Go to start it again.",
  abandoned:
    "You chose to send without a flyer. Invitations no longer require one.",
};

export function FlyerApproval({
  eventId,
  revision,
  accessToken,
}: {
  eventId: string;
  revision: number;
  accessToken: string;
}) {
  const [status, setStatus] = useState<AssetStatus>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reloads, setReloads] = useState(0);
  useEffect(() => {
    let active = true;
    loadAssetStatus(eventId, accessToken)
      .then(
        (value) => active && setStatus(value),
        (err) =>
          active && setError(failure(err, "Flyer status could not be loaded.")),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [eventId, accessToken, revision, reloads]);
  async function act(action: () => Promise<FlyerView>, done: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const flyer = await action();
      setStatus((current) => current && { ...current, flyer });
      setMessage(done);
    } catch (err) {
      setError(failure(err, "The flyer action failed."));
      // A conflict means Go or Canva moved on (new preview or revision): show the server's state.
      if (err instanceof ProviderRequestError && err.status === 409)
        setReloads((n) => n + 1);
    } finally {
      setBusy(false);
      setConfirmAbandon(false);
    }
  }
  const flyer = status?.flyer ?? null;
  const current = flyer?.event_revision === revision;
  const preview = current && flyer.stage === "previewed" ? flyer.preview : null;
  return (
    <section className="panel" aria-labelledby="flyer-approval">
      <h2 id="flyer-approval">Approve the Canva flyer</h2>
      {loading ? (
        <p role="status">Loading flyer status…</p>
      ) : status && !status.canva_connected ? (
        <p className="notice">
          Canva is not connected for your account, so Go cannot create or export
          a flyer yet.
        </p>
      ) : null}
      {status && !flyer && (
        <p className="muted">
          Go has not started a Canva flyer for this event.
        </p>
      )}
      {flyer && !current && (
        <p className="notice">
          The flyer is for revision {flyer.event_revision}, but the event is at
          revision {revision}. Ask Go to start a flyer for the current revision.
        </p>
      )}
      {flyer && current && (
        <>
          <p>
            <strong>Revision {flyer.event_revision}:</strong>{" "}
            {stageText[flyer.stage] ?? flyer.stage.replaceAll("_", " ")}
            {flyer.failure_code &&
              ` (${flyer.failure_code.replaceAll("_", " ")})`}
          </p>
          {preview && (
            <>
              <div className="asset-grid">
                {preview.thumbnail_urls.map((url, index) => (
                  <div className="asset-preview" key={url}>
                    <img
                      src={url}
                      alt={`Canva flyer preview, page ${index + 1}`}
                    />
                  </div>
                ))}
              </div>
              {preview.expected.length > 0 && (
                <>
                  <p className="muted">The flyer must show exactly:</p>
                  <dl className="expected-text">
                    {preview.expected.map(([key, value]) => (
                      <div key={key}>
                        <dt>{key.replaceAll("_", " ")}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              )}
              <p className="small muted">
                Preview fingerprint {preview.digest.slice(0, 12)}
              </p>
            </>
          )}
          {flyer.edit_url && (
            <a href={flyer.edit_url} target="_blank" rel="noreferrer">
              Edit in Canva ↗
            </a>
          )}
          <div className="button-row">
            <button
              disabled={busy || !preview}
              onClick={() =>
                preview &&
                act(
                  () =>
                    approveFlyer(
                      eventId,
                      revision,
                      preview.digest,
                      accessToken,
                    ),
                  "Flyer approved for this revision. Ask Go to export it.",
                )
              }
            >
              Approve this exact preview
            </button>
            {flyer.stage !== "abandoned" &&
              (confirmAbandon ? (
                <>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      act(
                        () => abandonFlyer(eventId, revision, accessToken),
                        "Flyer abandoned. Invitations will send without a flyer.",
                      )
                    }
                  >
                    Yes, send without a flyer
                  </button>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => setConfirmAbandon(false)}
                  >
                    Keep the flyer
                  </button>
                </>
              ) : (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => setConfirmAbandon(true)}
                >
                  Abandon flyer
                </button>
              ))}
          </div>
        </>
      )}
      <p role="status">{busy ? "Saving your flyer decision…" : message}</p>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

const calendarText: Record<string, string> = {
  create: "Create a new Calendar invitation",
  update: "Update the existing Calendar event",
};
const gmailText: Record<string, string> = {
  create_draft: "Create the Gmail invitation draft",
  replace_draft: "Replace the unsent Gmail draft",
  new_change_notice:
    "Send a new change notice (the earlier email was already sent)",
};

export function DistributionPreview({
  eventId,
  revision,
  accessToken,
}: {
  eventId: string;
  revision: number;
  accessToken: string;
}) {
  const [plan, setPlan] = useState<DistributionPlan>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    loadDistributionPlan(eventId, accessToken).then(
      (value) => active && setPlan(value),
      (err) => {
        if (!active) return;
        setError(
          err instanceof ProviderRequestError && err.code === "api_unavailable"
            ? "This server does not show the distribution preview yet. Ask Go to run preview_distribution for the blockers."
            : failure(err, "The distribution preview could not be loaded."),
        );
      },
    );
    return () => {
      active = false;
    };
  }, [eventId, accessToken, revision]);
  return (
    <section className="panel" aria-labelledby="distribution-preview">
      <h2 id="distribution-preview">What sending will do</h2>
      {error && <p role="alert">{error}</p>}
      {!plan && !error && (
        <p role="status">Loading the distribution preview…</p>
      )}
      {plan && plan.event_revision !== revision && (
        <p className="notice">
          This preview is for revision {plan.event_revision}; the event is at
          revision {revision}. Refresh before sending.
        </p>
      )}
      {plan && (
        <>
          <ul>
            <li>
              {calendarText[plan.calendar_action] ?? plan.calendar_action}
              {plan.calendar_event_id && ` (${plan.calendar_event_id})`}
            </li>
            <li>{gmailText[plan.gmail_action] ?? plan.gmail_action}</li>
            <li>
              {plan.invitee_count} invitee{plan.invitee_count === 1 ? "" : "s"}
            </li>
          </ul>
          {plan.blockers.length ? (
            <>
              <h3>Resolve before sending</h3>
              <ul aria-label="Distribution blockers">
                {plan.blockers.map((blocker) => (
                  <li key={`${blocker.code}:${blocker.message}`}>
                    <strong>{blocker.code.replaceAll("_", " ")}:</strong>{" "}
                    {blocker.message}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p role="status">
              The server reports no blockers for this revision.
            </p>
          )}
        </>
      )}
    </section>
  );
}
