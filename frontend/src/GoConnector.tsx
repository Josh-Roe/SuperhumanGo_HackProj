import { useEffect, useRef, useState } from "react";
import { issueGoConnector } from "./api";

export function GoConnector({
  accessToken,
  onCreated,
}: {
  accessToken: string;
  onCreated?: () => void;
}) {
  const [credential, setCredential] =
    useState<Awaited<ReturnType<typeof issueGoConnector>>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const tokenField = useRef<HTMLInputElement>(null);
  const createButton = useRef<HTMLButtonElement>(null);
  const hadCredential = useRef(false);
  useEffect(() => {
    if (credential) tokenField.current?.focus();
    else if (hadCredential.current) createButton.current?.focus();
    hadCredential.current = Boolean(credential);
  }, [credential]);
  return (
    <div className="go-key">
      {credential ? (
        <>
          <label>
            Your Go key
            <input
              ref={tokenField}
              type="password"
              readOnly
              value={credential.token}
              onFocus={(event) => event.currentTarget.select()}
              autoComplete="off"
            />
          </label>
          <p className="small muted">
            Copy it now: it’s hidden when you leave this page. It works until{" "}
            {new Date(credential.expires_at).toLocaleDateString()}.
          </p>
          <button
            className="secondary"
            onClick={() => setCredential(undefined)}
          >
            Hide key
          </button>
        </>
      ) : (
        <button
          className="secondary"
          ref={createButton}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              setCredential(await issueGoConnector(accessToken));
              onCreated?.();
            } catch (err) {
              setError(
                err instanceof Error
                  ? err.message
                  : "Could not create a key. Try again.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Creating…" : "Create Go key"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
