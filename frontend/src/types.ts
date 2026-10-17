export type WorkState =
  | "queued"
  | "awaiting_go"
  | "running"
  | "needs_review"
  | "ready"
  | "succeeded"
  | "failed"
  | "superseded";
export type ContentKind =
  | "description"
  | "plain_language_summary"
  | "invitation"
  | "change_notice"
  | "event_document"
  | "flyer_brief"
  | "flyer_copy"
  | "flyer_alt_text"
  | "notion_note";
export interface EventInput {
  title: string;
  description: string;
  location: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  organizer_contact: string;
  links: string[];
  invitees: { id: string; email: string; display_name?: string | null }[];
}
export interface EventRecord extends EventInput {
  id: string;
  revision: number;
  status: string;
  created_via?: "superhuman_go" | "manual";
}
export interface Content {
  id: string;
  kind: ContentKind;
  body: string;
  subject?: string | null;
  producer: "superhuman_go" | "organizer" | "gemini";
  event_revision: number;
  state: WorkState;
}
export interface Asset {
  id: string;
  kind: "flyer" | "document";
  event_revision: number;
  state: WorkState;
  preview_url?: string;
  current_url?: string;
  edit_url?: string;
  alt_text?: string;
}
export const factLabels = {
  step_free: "Step-free entrance",
  elevator: "Elevator / ground-floor route",
  diet: "Dietary options",
  observances: "Religious observances to check",
  captions: "Captions",
  loud_sound: "Loud sound",
  strobes: "Strobes",
} as const;
export type FactKey = keyof typeof factLabels;
export interface Fact {
  value: "yes" | "no" | "unknown";
  detail: string;
  source: string;
  confirmed_on: string;
}
export interface Finding {
  category: string;
  status: "recorded" | "attention" | "unknown" | "needs_review";
  reason: string;
  sources: { reference: string; checked_on: string }[];
}
export interface Operation {
  approval_id?: string;
  id: string;
  provider: string;
  kind: string;
  event_revision: number;
  state: WorkState;
  error_code?: string;
  receipt?: string;
}
export interface Rsvp {
  invitee_id: string;
  status:
    "attending" | "maybe" | "not_attending" | "no_response" | "needs_review";
  source: string;
  source_id: string;
  observed_at: string;
  event_revision: number;
  conflict?: boolean;
}
export interface WorkspaceEvent {
  live?: {
    warnings: string[];
    factsReadOnly: boolean;
    reviewAvailable: boolean;
    receiptsAvailable: boolean;
    rsvpsAvailable: boolean;
    approval?: {
      id: string;
      event_revision: number;
      action: "publish" | "update";
      invitation_content_id: string;
    };
  };
  event: EventRecord;
  content: Content[];
  work: { id: string; event_revision: number; state: WorkState }[];
  assets: Asset[];
  facts: Record<FactKey, Fact>;
  findings: Finding[];
  operations: Operation[];
  rsvps: Rsvp[];
  gmail: {
    sent: boolean;
    event_revision: number;
    draft_id?: string;
    message_id?: string;
  } | null;
  review_revision: number | null;
}
export interface Session {
  access_token: string;
  email: string;
  expires_at: number;
}
export interface EventGateway {
  mode: "preview" | "live";
  readOnly?: boolean;
  list(): Promise<EventRecord[]>;
  get(id: string): Promise<WorkspaceEvent>;
  save(
    id: string | null,
    input: EventInput,
    expected_revision?: number,
  ): Promise<WorkspaceEvent>;
  prepare(id: string, revision: number): Promise<WorkspaceEvent>;
  review(
    id: string,
    revision: number,
    content: Content[],
    facts: Record<FactKey, Fact>,
  ): Promise<WorkspaceEvent>;
  publish(
    id: string,
    revision: number,
    action: "publish" | "update",
    idempotency_key: string,
    invitation_content_id?: string,
  ): Promise<WorkspaceEvent>;
}
export function emptyFacts(): Record<FactKey, Fact> {
  return Object.fromEntries(
    Object.keys(factLabels).map((key) => [
      key,
      { value: "unknown", detail: "", source: "", confirmed_on: "" },
    ]),
  ) as Record<FactKey, Fact>;
}
export function safeUrl(value?: string): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
export function friendlyState(state: string): string {
  return state.replaceAll("_", " ");
}
