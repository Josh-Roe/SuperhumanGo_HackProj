// Inclusion facts in the server's own form (services.inclusion.InclusionInput), saved with
// GET/PUT /api/events/{id}/inclusion and optimistic `version` concurrency (A10).
import { providerJson } from "./providers";

export type Value = "yes" | "no" | "unknown";
export interface Source {
  label: string;
  confirmed_by: string;
  observed_at: string; // timezone-aware ISO 8601
  url: string | null;
}
export interface Fact {
  value: Value;
  source: Source | null;
}
export const factKeys = [
  "step_free_entrance",
  "above_ground_floor",
  "elevator",
  "food_served",
  "captions",
  "loud_sound",
  "strobes",
] as const;
export type FactKey = (typeof factKeys)[number];
export const traditions = [
  ["christian", "Christian"],
  ["jewish", "Jewish"],
  ["muslim", "Muslim"],
  ["hindu", "Hindu"],
  ["orthodox_christian", "Orthodox Christian"],
] as const;
export type Tradition = (typeof traditions)[number][0];

export type InclusionFacts = Record<FactKey, Fact> & {
  diet_options: string[];
  diet_source: Source | null;
  // Organizer-private and organizer-sourced extras: kept exactly as the server sent them.
  required_diets: unknown[];
  observances_selected: boolean;
  observances: unknown[];
  traditions: Tradition[];
};

export interface Finding {
  category: string;
  status: "recorded" | "attention" | "unknown" | "needs_review";
  reason: string;
  sources: Source[];
  conflicts: string[];
}

export interface InclusionView {
  version: number;
  saved_at_event_revision: number | null;
  review_revision: number;
  facts: InclusionFacts;
  findings: Finding[];
}

type Row = Record<string, unknown>;
function row(value: unknown): Row {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("The server returned invalid inclusion facts.");
  return value as Row;
}
const list = (value: unknown): unknown[] => {
  if (!Array.isArray(value))
    throw new Error("The server returned invalid inclusion facts.");
  return value;
};
const text = (value: unknown) => (typeof value === "string" ? value : "");

function source(value: unknown): Source | null {
  if (value === null || value === undefined) return null;
  const s = row(value);
  return {
    label: text(s.label),
    confirmed_by: text(s.confirmed_by),
    observed_at: text(s.observed_at),
    url: text(s.url) || null,
  };
}
function fact(value: unknown): Fact {
  const f = row(value ?? {});
  const v = f.value ?? "unknown";
  if (v !== "yes" && v !== "no" && v !== "unknown")
    throw new Error("The server returned an invalid inclusion fact.");
  return { value: v, source: source(f.source) };
}
const statuses = ["recorded", "attention", "unknown", "needs_review"];

export function parseInclusion(raw: unknown, eventId: string): InclusionView {
  const value = row(raw);
  const review = row(value.review);
  if (value.event_id !== eventId || review.event_id !== eventId)
    throw new Error("The server returned inclusion facts for another event.");
  if (
    !Number.isInteger(value.version) ||
    !Number.isInteger(review.event_revision)
  )
    throw new Error("The server returned invalid inclusion facts.");
  const f = row(value.facts);
  const known = traditions.map(([key]) => key as string);
  return {
    version: value.version as number,
    saved_at_event_revision: Number.isInteger(value.saved_at_event_revision)
      ? (value.saved_at_event_revision as number)
      : null,
    review_revision: review.event_revision as number,
    facts: {
      ...(Object.fromEntries(
        factKeys.map((key) => [key, fact(f[key])]),
      ) as Record<FactKey, Fact>),
      diet_options: list(f.diet_options ?? [])
        .map(text)
        .filter(Boolean),
      diet_source: source(f.diet_source),
      required_diets: list(f.required_diets ?? []),
      observances_selected: f.observances_selected === true,
      observances: list(f.observances ?? []),
      traditions: list(f.traditions ?? known)
        .map(text)
        .filter((t): t is Tradition => known.includes(t)),
    },
    findings: list(review.findings).map((item) => {
      const finding = row(item);
      if (!statuses.includes(text(finding.status)))
        throw new Error("The server returned an invalid inclusion finding.");
      return {
        category: text(finding.category),
        status: finding.status as Finding["status"],
        reason: text(finding.reason),
        sources: list(finding.sources ?? [])
          .map(source)
          .filter((s): s is Source => s !== null),
        conflicts: list(finding.conflicts ?? [])
          .map(text)
          .filter(Boolean),
      };
    }),
  };
}

const path = (id: string) => `/api/events/${encodeURIComponent(id)}/inclusion`;

export async function loadInclusion(
  eventId: string,
  token: string,
): Promise<InclusionView> {
  return parseInclusion(await providerJson(path(eventId), token), eventId);
}

export async function saveInclusion(
  eventId: string,
  expectedVersion: number,
  facts: InclusionFacts,
  token: string,
): Promise<InclusionView> {
  return parseInclusion(
    await providerJson(path(eventId), token, "PUT", {
      expected_version: expectedVersion,
      facts,
    }),
    eventId,
  );
}
