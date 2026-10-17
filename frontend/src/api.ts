import { normalizeContentKind } from "./content";
import { emptyFacts } from "./types";
export interface ProjectStatus {
  superhuman: {
    transport: "mcp";
    configured: boolean;
    verified: false;
    endpoint: "/mcp";
  };
  model: {
    configured: boolean;
    runtime: "onnxruntime-cpu" | "not_configured";
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new Error(`Backend returned HTTP ${response.status}.`);
  return response.json();
}

export async function loadProjectStatus(
  signal: AbortSignal,
): Promise<ProjectStatus> {
  const [health, status] = await Promise.all([
    getJson("/api/health", signal),
    getJson("/api/status", signal),
  ]);
  if (
    !isRecord(health) ||
    health.status !== "ok" ||
    health.service !== "backend"
  ) {
    throw new Error("Backend health response did not match the API contract.");
  }
  if (
    !isRecord(status) ||
    !isRecord(status.superhuman) ||
    !isRecord(status.model)
  ) {
    throw new Error("Backend status response did not match the API contract.");
  }
  const { superhuman, model } = status;
  if (
    superhuman.transport !== "mcp" ||
    typeof superhuman.configured !== "boolean" ||
    superhuman.verified !== false ||
    superhuman.endpoint !== "/mcp" ||
    typeof model.configured !== "boolean" ||
    !["onnxruntime-cpu", "not_configured"].includes(String(model.runtime))
  ) {
    throw new Error("Backend status response did not match the API contract.");
  }
  return status as unknown as ProjectStatus;
}

// Proposed REST v0 boundary; enable only after Member 2 accepts this schema.
import type {
  EventGateway,
  EventRecord,
  Session,
  WorkspaceEvent,
} from "./types";
const states = [
  "queued",
  "awaiting_go",
  "running",
  "needs_review",
  "ready",
  "succeeded",
  "failed",
  "superseded",
];
export function parseEvent(value: unknown): EventRecord {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    !Number.isInteger(value.revision) ||
    Number(value.revision) < 1 ||
    ![
      "title",
      "description",
      "location",
      "starts_at",
      "ends_at",
      "timezone",
      "organizer_contact",
      "status",
    ].every((key) => typeof value[key] === "string") ||
    !Array.isArray(value.links) ||
    !value.links.every((link) => typeof link === "string") ||
    !Array.isArray(value.invitees) ||
    !value.invitees.every(
      (person) =>
        isRecord(person) &&
        typeof person.id === "string" &&
        typeof person.email === "string",
    )
  )
    throw new Error("Event response did not match the proposed API contract.");
  try {
    new Intl.DateTimeFormat("en", { timeZone: String(value.timezone) });
  } catch {
    throw new Error("Event timezone is invalid.");
  }
  if (
    !Number.isFinite(Date.parse(String(value.starts_at))) ||
    Date.parse(String(value.ends_at)) <= Date.parse(String(value.starts_at)) ||
    !Number.isFinite(Date.parse(String(value.ends_at)))
  )
    throw new Error("Event timestamps are invalid.");
  return value as unknown as EventRecord;
}
function normalizeAsset(
  value: unknown,
  eventId: string,
): Record<string, unknown> {
  if (
    !isRecord(value) ||
    (value.event_id !== undefined && value.event_id !== eventId)
  )
    throw new Error("Artifact response did not match this event.");
  const kind =
    value.kind === "flyer_png"
      ? "flyer"
      : value.kind === "event_document"
        ? "document"
        : value.kind;
  const state =
    value.state ??
    (value.review_state === "reviewed"
      ? "ready"
      : value.review_state === "needs_review"
        ? "needs_review"
        : undefined);
  // Member 4 preview metadata uses a content hash, not a provider/database ID. This is a UI key only.
  const id =
    value.id ??
    (typeof value.sha256 === "string" && /^[a-f0-9]{64}$/.test(value.sha256)
      ? `${kind}:${value.event_revision}:${value.sha256}`
      : undefined);
  return { ...value, kind, state, id };
}
export function parseWorkspace(raw: unknown): WorkspaceEvent {
  const fail = () => {
    throw new Error("Review response did not match the proposed API contract.");
  };
  if (!isRecord(raw)) return fail();
  const event = parseEvent(raw.event);
  const value: Record<string, unknown> = {
    ...raw,
    assets: Array.isArray(raw.assets)
      ? raw.assets.map((asset) => normalizeAsset(asset, event.id))
      : raw.assets,
  };
  const collections = [
    "content",
    "work",
    "assets",
    "findings",
    "operations",
    "rsvps",
  ];
  if (!collections.every((key) => Array.isArray(value[key]))) return fail();
  for (const key of ["content", "work", "assets", "operations"]) {
    for (const item of value[key] as unknown[]) {
      if (
        !isRecord(item) ||
        typeof item.id !== "string" ||
        !Number.isInteger(item.event_revision) ||
        Number(item.event_revision) < 1 ||
        (item.event_id !== undefined && item.event_id !== event.id) ||
        !states.includes(String(item.state))
      )
        return fail();
    }
  }
  if (
    !(value.content as unknown[]).every(
      (c) =>
        isRecord(c) &&
        typeof c.body === "string" &&
        ["superhuman_go", "organizer"].includes(String(c.producer)) &&
        (c.subject === undefined ||
          c.subject === null ||
          typeof c.subject === "string"),
    )
  )
    return fail();
  if (
    !(value.assets as unknown[]).every(
      (a) =>
        isRecord(a) &&
        ["flyer", "document"].includes(String(a.kind)) &&
        ["preview_url", "edit_url", "current_url", "alt_text"].every(
          (k) => a[k] === undefined || typeof a[k] === "string",
        ),
    )
  )
    return fail();
  if (
    !(value.operations as unknown[]).every(
      (o) =>
        isRecord(o) &&
        typeof o.provider === "string" &&
        typeof o.kind === "string" &&
        (o.receipt === undefined || typeof o.receipt === "string") &&
        (o.error_code === undefined || typeof o.error_code === "string"),
    )
  )
    return fail();
  if (
    !(value.findings as unknown[]).every(
      (f) =>
        isRecord(f) &&
        typeof f.category === "string" &&
        typeof f.reason === "string" &&
        ["recorded", "attention", "unknown", "needs_review"].includes(
          String(f.status),
        ) &&
        Array.isArray(f.sources) &&
        f.sources.every(
          (s) =>
            isRecord(s) &&
            typeof s.reference === "string" &&
            typeof s.checked_on === "string",
        ),
    )
  )
    return fail();
  if (
    !(value.rsvps as unknown[]).every(
      (r) =>
        isRecord(r) &&
        [
          "attending",
          "maybe",
          "not_attending",
          "no_response",
          "needs_review",
        ].includes(String(r.status)) &&
        ["invitee_id", "source", "source_id", "observed_at"].every(
          (k) => typeof r[k] === "string",
        ) &&
        Number.isInteger(r.event_revision) &&
        (r.conflict === undefined || typeof r.conflict === "boolean"),
    )
  )
    return fail();
  if (
    !isRecord(value.facts) ||
    ![
      "step_free",
      "elevator",
      "diet",
      "observances",
      "captions",
      "loud_sound",
      "strobes",
    ].every((key) => {
      const fact = (value.facts as Record<string, unknown>)[key];
      return (
        isRecord(fact) &&
        ["yes", "no", "unknown"].includes(String(fact.value)) &&
        ["detail", "source", "confirmed_on"].every(
          (k) => typeof fact[k] === "string",
        )
      );
    })
  )
    return fail();
  if (
    value.review_revision !== null &&
    !Number.isInteger(value.review_revision)
  )
    return fail();
  if (
    value.gmail !== null &&
    (!isRecord(value.gmail) ||
      typeof value.gmail.sent !== "boolean" ||
      !Number.isInteger(value.gmail.event_revision))
  )
    return fail();
  const content = (value.content as Record<string, unknown>[]).map((item) => ({
    ...item,
    kind: normalizeContentKind(item.kind),
  }));
  if (
    new Set((value.content as Record<string, unknown>[]).map((item) => item.id))
      .size !== content.length
  )
    return fail();
  return { ...value, content } as unknown as WorkspaceEvent;
}
export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}
export async function requestJson(
  path: string,
  token: string,
  method = "GET",
  body?: unknown,
  idempotencyKey?: string,
): Promise<unknown> {
  const response = await fetch(path, {
    method,
    signal: AbortSignal.timeout(12000),
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const code =
      response.status === 401
        ? "unauthenticated"
        : response.status === 403
          ? "forbidden"
          : response.status === 409
            ? "revision_conflict"
            : response.status === 404
              ? "api_unavailable"
              : "provider_failed";
    const messages: Record<string, string> = {
      unauthenticated: "Your session expired. Sign in again.",
      forbidden: "You do not have access to this event.",
      revision_conflict:
        "Go or another session changed this event. Reload the current revision before saving.",
      api_unavailable:
        "The event service is not available yet. You can return to the local preview.",
      provider_failed: `The request failed (HTTP ${response.status}). Refresh status before retrying.`,
    };
    throw new ApiError(code, messages[code]);
  }
  return response.status === 204 ? null : response.json();
}
function supabaseOrigin(config?: PublicAuthConfig): string {
  const url = new URL(
    config?.supabase_url ?? import.meta.env.VITE_SUPABASE_URL,
  );
  if (
    url.username ||
    url.password ||
    (url.protocol !== "https:" &&
      !(
        url.protocol === "http:" &&
        ["localhost", "127.0.0.1"].includes(url.hostname)
      ))
  )
    throw new Error("Supabase requires HTTPS.");
  return url.origin;
}
function publishableKey(config?: PublicAuthConfig): string {
  return (
    config?.supabase_publishable_key ??
    import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
  );
}
async function tokenSession(
  config: PublicAuthConfig | undefined,
  grant: string,
  body: unknown,
  failure: string,
): Promise<Session> {
  const response = await fetch(
    `${supabaseOrigin(config)}/auth/v1/token?grant_type=${grant}`,
    {
      method: "POST",
      signal: AbortSignal.timeout(12000),
      headers: {
        apikey: publishableKey(config),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) throw new Error(failure);
  const data: unknown = await response.json();
  if (
    !isRecord(data) ||
    typeof data.access_token !== "string" ||
    typeof data.expires_in !== "number" ||
    !Number.isFinite(data.expires_in) ||
    data.expires_in <= 0 ||
    !isRecord(data.user) ||
    typeof data.user.email !== "string"
  )
    throw new Error("Supabase returned an invalid session.");
  return {
    access_token: data.access_token,
    email: data.user.email,
    expires_at: Date.now() + data.expires_in * 1000,
  };
}
// Google sign-in through Supabase Auth's PKCE flow. The verifier and the public
// config survive the redirect in sessionStorage; tokens never appear in the URL.
const GOOGLE_PENDING = "google-sign-in";
const CALLBACK_PARAMS = ["code", "error", "error_code", "error_description"];
function base64Url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
export async function googleSignInUrl(
  config: PublicAuthConfig,
): Promise<string> {
  const origin = supabaseOrigin(config);
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = base64Url(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)),
    ),
  );
  sessionStorage.setItem(GOOGLE_PENDING, JSON.stringify({ verifier, config }));
  const url = new URL(`${origin}/auth/v1/authorize`);
  url.searchParams.set("provider", "google");
  url.searchParams.set("redirect_to", location.href.split("#")[0]);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "s256");
  return url.href;
}
// Returns null when this page load is not a Google sign-in return.
export async function completeGoogleSignIn(): Promise<Session | null> {
  const params = new URLSearchParams(location.search);
  if (!CALLBACK_PARAMS.some((name) => params.has(name))) return null;
  const code = params.get("code");
  const denied = params.get("error_description") ?? params.get("error");
  const raw = sessionStorage.getItem(GOOGLE_PENDING);
  sessionStorage.removeItem(GOOGLE_PENDING);
  const cleaned = new URL(location.href);
  for (const name of CALLBACK_PARAMS) cleaned.searchParams.delete(name);
  history.replaceState(history.state, "", cleaned);
  if (!raw) {
    if (!code && !denied) return null;
    throw new Error("Google sign-in expired. Sign in with Google again.");
  }
  if (denied || !code)
    throw new Error(`Google sign-in did not finish: ${denied ?? "no code"}.`);
  const pending: unknown = JSON.parse(raw);
  if (
    !isRecord(pending) ||
    typeof pending.verifier !== "string" ||
    !isRecord(pending.config) ||
    typeof pending.config.supabase_url !== "string" ||
    typeof pending.config.supabase_publishable_key !== "string"
  )
    throw new Error("Google sign-in expired. Sign in with Google again.");
  return tokenSession(
    {
      supabase_url: pending.config.supabase_url,
      supabase_publishable_key: pending.config.supabase_publishable_key,
    },
    "pkce",
    { auth_code: code, code_verifier: pending.verifier },
    "Google sign-in failed. Check that the Google provider is enabled in Supabase Auth.",
  );
}

// Member 2's published canonical event REST contract. Narrow, read-only transfer test.
export function createEventTransferGateway(token: string): EventGateway {
  const blocked = async (): Promise<WorkspaceEvent> => {
    throw new Error(
      "This connection tests event details only. Editing and distribution are not enabled.",
    );
  };
  return {
    mode: "live",
    readOnly: true,
    async list() {
      const events: EventRecord[] = [];
      for (let offset = 0; ; offset += 100) {
        const rows = await requestJson(
          `/api/events?limit=100&offset=${offset}`,
          token,
        );
        if (!Array.isArray(rows))
          throw new Error("Event list must be an array.");
        events.push(...rows.map(parseEvent));
        if (rows.length < 100) return events;
      }
    },
    async get(id) {
      const event = parseEvent(
        await requestJson(`/api/events/${encodeURIComponent(id)}`, token),
      );
      if (event.id !== id)
        throw new Error("The server returned a different event.");
      return {
        event,
        content: [],
        assets: [],
        work: [],
        facts: emptyFacts(),
        findings: [],
        operations: [],
        rsvps: [],
        gmail: null,
        review_revision: null,
      };
    },
    save: blocked,
    prepare: blocked,
    review: blocked,
    publish: blocked,
  };
}
export interface PublicAuthConfig {
  supabase_url: string;
  supabase_publishable_key: string;
}
export async function loadPublicAuthConfig(): Promise<PublicAuthConfig> {
  const response = await fetch("/api/config", {
    signal: AbortSignal.timeout(8000),
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    if (response.status === 404)
      throw new Error(
        "The event API is not registered on this backend yet. The connection test cannot run.",
      );
    throw new Error(
      `The event API is unavailable (HTTP ${response.status}). Check backend hosting and Vercel BACKEND_ORIGIN, then retry.`,
    );
  }
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new Error(
      "The event API returned invalid data. Check that /api/config reaches the Python backend.",
    );
  }
  if (
    !isRecord(value) ||
    value.configured !== true ||
    typeof value.supabase_url !== "string" ||
    typeof value.supabase_publishable_key !== "string"
  )
    throw new Error(
      "The backend needs public Supabase authentication configuration.",
    );
  return {
    supabase_url: value.supabase_url,
    supabase_publishable_key: value.supabase_publishable_key,
  };
}

export async function issueGoConnector(
  token: string,
): Promise<{ id: string; token: string; expires_at: string }> {
  const value = await requestJson("/api/connectors", token, "POST", {
    label: "Superhuman Go",
    expires_in_days: 30,
  });
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    typeof value.token !== "string" ||
    !/^go_[A-Za-z0-9_-]{40,}$/.test(value.token) ||
    typeof value.expires_at !== "string" ||
    !Number.isFinite(Date.parse(value.expires_at))
  )
    throw new Error("The server returned invalid connector credentials.");
  return value as { id: string; token: string; expires_at: string };
}
