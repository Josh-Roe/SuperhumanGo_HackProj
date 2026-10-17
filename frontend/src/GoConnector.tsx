import { useState } from "react";
import { issueGoConnector } from "./api";

export function GoConnector({ accessToken }: { accessToken: string }) {
  const [credential, setCredential] =
    useState<Awaited<ReturnType<typeof issueGoConnector>>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <section className="panel">
      <h2>Authorize Go for your events</h2>
      <p>
        Create a personal connector token, then paste it into the connector’s
        authentication setting in Go. Keep it out of chat prompts. It grants
        access to this organizer’s event tools.
      </p>
      {credential ? (
        <>
          <label>
            Personal Go connector token
            <input
              type="password"
              readOnly
              value={credential.token}
              onFocus={(event) => event.currentTarget.select()}
              autoComplete="off"
            />
          </label>
          <p className="small muted">
            Select the field and copy it. Expires{" "}
            {new Date(credential.expires_at).toLocaleDateString()}. This value
            disappears when you leave Settings; the authorization stays active
            until expiry or server revocation.
          </p>
          <button
            className="secondary"
            onClick={() => setCredential(undefined)}
          >
            Hide token
          </button>
        </>
      ) : (
        <button
          className="secondary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              setCredential(await issueGoConnector(accessToken));
            } catch (err) {
              setError(
                err instanceof Error
                  ? err.message
                  : "Could not authorize the connector.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Creating…" : "Create personal Go token"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
