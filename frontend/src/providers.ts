// Organizer-facing provider transport: Google/Canva connection, Canva flyer approval and the
// distribution preview. Every response is validated before the UI trusts it.
import { safeUrl } from "./types";

export type Provider = "google" | "canva";
export const providerNames: Record<Provider, string> = {
  google: "Google",
  canva: "Canva",
};

export class ProviderRequestError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

type Row = Record<string, unknown>;
function row(value: unknown, what: string): Row {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(`The server returned an invalid ${what}.`);
  return value as Row;
}
const text = (value: unknown) => (typeof value === "string" ? value : "");

const fallback: Record<number, [string, string]> = {
  401: ["unauthenticated", "Your session expired. Sign in again."],
  403: ["forbidden", "You do not have access to this event."],
  404: [
    "api_unavailable",
    "This server does not offer that action yet. Refresh status before retrying.",
  ],
};

export async function providerJson(
  path: string,
  token: string,
  method = "GET",
  body?: unknown,
): Promise<unknown> {
  const response = await fetch(path, {
    method,
    signal: AbortSignal.timeout(12000),
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (response.ok) return response.json();
  let detail: unknown;
  try {
    detail = ((await response.json()) as Row | null)?.detail;
  } catch {
    detail = undefined;
  }
  // Server errors carry {detail: {code, message}}. FastAPI's own 404 for an unknown route is a string.
  if (detail && typeof detail === "object" && text((detail as Row).code)) {
    const { code, message } = detail as Row;
    throw new ProviderRequestError(
      text(code),
      text(message) || `The request failed (HTTP ${response.status}).`,
      response.status,
    );
  }
  const [code, message] = fallback[response.status] ?? [
    "provider_failed",
    `The request failed (HTTP ${response.status}). Refresh status before retrying.`,
  ];
  throw new ProviderRequestError(code, message, response.status);
}

// Connections -------------------------------------------------------------------------------

export interface Connection {
  connected: boolean;
  email: string | null;
}

export async function loadConnection(
  provider: Provider,
  token: string,
): Promise<Connection> {
  const value = row(
    await providerJson(`/api/${provider}/status`, token),
    "connection status",
  );
  if (typeof value.connected !== "boolean")
    throw new Error("The server returned an invalid connection status.");
  return {
    connected: value.connected,
    email: value.connected && text(value.email) ? text(value.email) : null,
  };
}

export async function startConnection(
  provider: Provider,
  token: string,
): Promise<string> {
  const value = row(
    await providerJson(`/api/${provider}/connect`, token, "POST"),
    "authorization link",
  );
  const url = safeUrl(text(value.authorization_url));
  if (!url)
    throw new Error("The server returned an unsafe authorization link.");
  return url;
}

// OAuth callback flags (A13): ?google=connected | ?google=error&reason=… on APP_URL ------------

export interface CallbackResult {
  provider: Provider;
  ok: boolean;
  message: string;
}

const reasons: Record<string, (name: string) => string> = {
  invalid_state: (name) =>
    `The ${name} sign-in link expired or was already used. Nothing was connected. Start Connect ${name} again from Settings.`,
  denied: (name) => `${name} access was not granted. Nothing was connected.`,
  exchange_failed: (name) =>
    `${name} sign-in could not be completed. Nothing was connected. Try Connect ${name} again.`,
  no_refresh_token: (name) =>
    `${name} did not grant offline access, so nothing was connected. Remove this app's access in your ${name} account settings, then connect again.`,
};

/** Reads one provider callback flag and returns the URL without the callback parameters. */
export function readCallback(url: string): {
  result: CallbackResult | null;
  cleaned: string;
} {
  const parsed = new URL(url);
  const params = parsed.searchParams;
  const provider = (["google", "canva"] as const).find((p) => params.has(p));
  if (!provider) return { result: null, cleaned: url };
  const flag = params.get(provider);
  const reason = params.get("reason") ?? "";
  for (const key of ["google", "canva", "reason"]) params.delete(key);
  const name = providerNames[provider];
  const result: CallbackResult =
    flag === "connected"
      ? {
          provider,
          ok: true,
          message: `${name} is connected. Sign in to your workspace in Settings to see the connected account.`,
        }
      : {
          provider,
          ok: false,
          message:
            reasons[reason]?.(name) ??
            `${name} could not be connected. Nothing was changed; try again from Settings.`,
        };
  return { result, cleaned: parsed.toString() };
}

// Canva flyer (GET /api/events/{id}/assets) ----------------------------------------------------

export interface FlyerView {
  event_revision: number;
  stage: string;
  failure_code: string | null;
  preview: {
    digest: string;
    expected: [string, string][];
    thumbnail_urls: string[];
  } | null;
  edit_url?: string;
  organizer_reviewed: boolean;
}

export interface AssetStatus {
  flyer: FlyerView | null;
  canva_connected: boolean;
  storage_configured: boolean;
}

function parseFlyer(raw: unknown, eventId: string): FlyerView | null {
  if (raw === null || raw === undefined) return null;
  const value = row(raw, "flyer");
  if (value.event_id !== eventId)
    throw new Error("The server returned a flyer for another event.");
  if (!Number.isInteger(value.event_revision) || !text(value.stage))
    throw new Error("The server returned an invalid flyer.");
  let preview: FlyerView["preview"] = null;
  if (value.preview) {
    const p = row(value.preview, "flyer preview");
    if (!/^[a-f0-9]{64}$/.test(text(p.digest)))
      throw new Error("The server returned an invalid flyer preview.");
    preview = {
      digest: text(p.digest),
      expected: Object.entries(row(p.expected ?? {}, "flyer preview")).map(
        ([key, v]) => [key, text(v)],
      ),
      thumbnail_urls: (Array.isArray(p.thumbnail_urls) ? p.thumbnail_urls : [])
        .map((u) => safeUrl(text(u)))
        .filter((u): u is string => Boolean(u)),
    };
  }
  const design = value.design ? row(value.design, "flyer design") : {};
  const verified = value.verified ? row(value.verified, "flyer check") : {};
  return {
    event_revision: value.event_revision as number,
    stage: text(value.stage),
    failure_code: text(value.failure_code) || null,
    preview,
    edit_url: safeUrl(text(design.edit_url)),
    organizer_reviewed: verified.organizer_reviewed === true,
  };
}

const assetPath = (id: string) =>
  `/api/events/${encodeURIComponent(id)}/assets`;

export async function loadAssetStatus(
  eventId: string,
  token: string,
): Promise<AssetStatus> {
  const value = row(
    await providerJson(assetPath(eventId), token),
    "asset status",
  );
  return {
    flyer: parseFlyer(value.flyer, eventId),
    canva_connected: value.canva === "connected",
    storage_configured: value.storage === "configured",
  };
}

export async function approveFlyer(
  eventId: string,
  revision: number,
  digest: string,
  token: string,
): Promise<FlyerView> {
  const flyer = parseFlyer(
    await providerJson(`${assetPath(eventId)}/flyer/approve`, token, "POST", {
      expected_revision: revision,
      preview_digest: digest,
    }),
    eventId,
  );
  if (!flyer) throw new Error("The server returned no flyer.");
  return flyer;
}

export async function abandonFlyer(
  eventId: string,
  revision: number,
  token: string,
): Promise<FlyerView> {
  const flyer = parseFlyer(
    await providerJson(`${assetPath(eventId)}/flyer/abandon`, token, "POST", {
      expected_revision: revision,
    }),
    eventId,
  );
  if (!flyer) throw new Error("The server returned no flyer.");
  return flyer;
}

// Distribution preview (DistributionPlan from preview_distribution) ---------------------------
// Proposed REST route: GET /api/events/{id}/distribution/preview. Only the MCP tool exists today.

export interface DistributionPlan {
  event_revision: number;
  calendar_action: string;
  calendar_event_id: string | null;
  gmail_action: string;
  invitee_count: number;
  blockers: { code: string; message: string }[];
}

export async function loadDistributionPlan(
  eventId: string,
  token: string,
): Promise<DistributionPlan> {
  const value = row(
    await providerJson(
      `/api/events/${encodeURIComponent(eventId)}/distribution/preview`,
      token,
    ),
    "distribution preview",
  );
  if (value.event_id !== eventId)
    throw new Error("The server returned a preview for another event.");
  if (
    !Number.isInteger(value.event_revision) ||
    !Number.isInteger(value.invitee_count) ||
    !Array.isArray(value.blockers)
  )
    throw new Error("The server returned an invalid distribution preview.");
  return {
    event_revision: value.event_revision as number,
    calendar_action: text(value.calendar_action),
    calendar_event_id: text(value.calendar_event_id) || null,
    gmail_action: text(value.gmail_action),
    invitee_count: value.invitee_count as number,
    // Blockers are "code: message" strings, e.g. "needs_review: no invitees".
    blockers: value.blockers.map((b) => {
      const [code, ...rest] = text(b).split(": ");
      return rest.length
        ? { code, message: rest.join(": ") }
        : { code: "blocked", message: code };
    }),
  };
}
