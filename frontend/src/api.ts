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
export function parseWorkspace(value: unknown): WorkspaceEvent {
  const fail = () => {
    throw new Error("Review response did not match the proposed API contract.");
  };
  if (!isRecord(value)) return fail();
  parseEvent(value.event);
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
        ["superhuman_go", "organizer", "gemini"].includes(String(c.producer)) &&
        [
          "description",
          "plain_language_summary",
          "invitation",
          "change_notice",
          "event_document",
        ].includes(String(c.kind)),
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
  return value as unknown as WorkspaceEvent;
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
  return response.json();
}
export function createLiveGateway(token: string): EventGateway {
  const path = (id: string) => `/api/events/${encodeURIComponent(id)}`;
  const workspace = async (
    url: string,
    method?: string,
    body?: unknown,
    key?: string,
  ) => parseWorkspace(await requestJson(url, token, method, body, key));
  return {
    mode: "live",
    async list() {
      const response = await requestJson("/api/events", token);
      if (!Array.isArray(response))
        throw new Error("Event list must be an array.");
      return response.map(parseEvent);
    },
    get: (id) => workspace(path(id)),
    save: (id, input, revision) =>
      workspace(id ? path(id) : "/api/events", id ? "PATCH" : "POST", {
        ...input,
        ...(id ? { expected_revision: revision } : {}),
      }),
    prepare: (id, revision) =>
      workspace(`${path(id)}/prepare`, "POST", { expected_revision: revision }),
    review: (id, revision, content, facts) =>
      workspace(`${path(id)}/review`, "POST", {
        expected_revision: revision,
        content,
        facts,
        acknowledge_unknowns: true,
      }),
    publish: (id, revision, action, key) =>
      workspace(
        `${path(id)}/${action === "update" ? "sync" : "publish"}`,
        "POST",
        { expected_revision: revision, action, idempotency_key: key },
        key,
      ),
  };
}
export const authConfigured = Boolean(
  import.meta.env.VITE_SUPABASE_URL &&
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY &&
  import.meta.env.VITE_EVENT_API_ENABLED === "true",
);
export async function signIn(
  email: string,
  password: string,
): Promise<Session> {
  if (!authConfigured)
    throw new Error(
      "Live sign-in is awaiting a connected organizer account. Use the local preview.",
    );
  const url = new URL(import.meta.env.VITE_SUPABASE_URL);
  if (
    url.protocol !== "https:" &&
    !["localhost", "127.0.0.1"].includes(url.hostname)
  )
    throw new Error("Supabase requires HTTPS.");
  const response = await fetch(
    `${url.origin}/auth/v1/token?grant_type=password`,
    {
      method: "POST",
      signal: AbortSignal.timeout(12000),
      headers: {
        apikey: import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    },
  );
  if (!response.ok)
    throw new Error(
      "Sign-in failed. Check your credentials and Supabase email/password settings.",
    );
  const data: unknown = await response.json();
  if (
    !isRecord(data) ||
    typeof data.access_token !== "string" ||
    typeof data.expires_in !== "number" ||
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
