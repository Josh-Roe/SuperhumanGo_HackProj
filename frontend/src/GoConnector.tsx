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
  const [revealed, setRevealed] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");
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
              type={revealed ? "text" : "password"}
              readOnly
              value={credential.token}
              onFocus={(event) => event.currentTarget.select()}
              autoComplete="off"
            />
          </label>
          <p className="small muted">
            Copy it now: it disappears when you leave this page. It works until{" "}
            {new Date(credential.expires_at).toLocaleDateString()}.
          </p>
          <div className="action-row">
            <button
              className="primary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(credential.token);
                  setCopyMessage(
                    "Key copied. Now paste it into Go (step 3).",
                  );
                } catch {
                  setRevealed(true);
                  tokenField.current?.focus();
                  tokenField.current?.select();
                  setCopyMessage("Copy is blocked. Select the revealed key and press Command+C (Mac) or Ctrl+C.");
                }
              }}
            >
              Copy key
            </button>
            <button
              className="secondary"
              onClick={() => setRevealed(!revealed)}
              aria-pressed={revealed}
            >
              {revealed ? "Mask key" : "Show key"}
            </button>
          </div>
          {copyMessage && <p role="status">{copyMessage}</p>}
          <button
            className="secondary"
            onClick={() => {
              setCredential(undefined);
              setRevealed(false);
              setCopyMessage("");
            }}
          >
            Hide key
          </button>
        </>
      ) : (
        <button
          className="primary"
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
