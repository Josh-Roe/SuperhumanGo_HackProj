import {
  ApiError,
  createEventTransferGateway,
  parseEvent,
  parseWorkspace,
  requestJson,
} from "./api";
import { normalizeContentKind } from "./content";
import { emptyFacts, safeUrl } from "./types";
import type { EventGateway, WorkspaceEvent } from "./types";

type Row = Record<string, unknown>;
const row = (value: unknown): Row => {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Invalid organizer API response.");
  return value as Row;
};
const rows = (value: unknown): Row[] => {
  if (!Array.isArray(value)) throw new Error("Expected an organizer API list.");
  return value.map(row);
};
function scoped(value: Row, id: string) {
  if (value.event_id !== id)
    throw new Error("The server returned material for another event.");
  return value;
}

export function createOrganizerGateway(token: string): EventGateway {
  const read = createEventTransferGateway(token);
  const path = (id: string) => `/api/events/${encodeURIComponent(id)}`;
  const queued = new Map<string, WorkspaceEvent["work"][number]>();
  const approvals = new Map<
    string,
    NonNullable<WorkspaceEvent["live"]>["approval"]
  >();
  const approvalRequests = new Map<
    string,
    Promise<NonNullable<NonNullable<WorkspaceEvent["live"]>["approval"]>>
  >();
  const creationKeys = new Map<string, string>();

  async function get(id: string): Promise<WorkspaceEvent> {
    const event = parseEvent(await requestJson(path(id), token));
    if (event.id !== id)
      throw new Error("The server returned a different event.");
    const warnings = [
      "Inclusion answers are read-only here. Canva preview approval is not connected yet.",
    ];
    async function optional(
      url: string,
      label: string,
    ): Promise<unknown | undefined> {
      try {
        return await requestJson(url, token);
      } catch (error) {
        if (
          error instanceof ApiError &&
          ["unauthenticated", "forbidden", "revision_conflict"].includes(
            error.code,
          )
        )
          throw error;
        warnings.push(
          `${label} could not be loaded. Refresh before relying on this section.`,
        );
        return undefined;
      }
    }
    const [reviewRaw, operationRaw, rsvpRaw, flyerRaw, documentRaw] =
      await Promise.all([
        optional(`${path(id)}/review`, "Writing and inclusion"),
        optional(`${path(id)}/operations`, "Provider receipts"),
        optional(`${path(id)}/rsvps`, "Guest responses"),
        optional(`${path(id)}/artifacts/flyer_png/current`, "Current flyer"),
        optional(
          `${path(id)}/artifacts/event_document/current`,
          "Current document",
        ),
      ]);
    const review = reviewRaw === undefined ? undefined : row(reviewRaw);
    if (review) {
      const reviewedEvent = parseEvent(review.event);
      if (reviewedEvent.id !== id || reviewedEvent.revision !== event.revision)
        throw new ApiError(
          "revision_conflict",
          "The event changed while loading its material. Refresh to read one revision.",
        );
    }
    // Reviews that edit prose create a new content ID. Use the latest stored output per kind/revision.
    const latest = new Map<string, Row>();
    for (const item of review ? rows(review.generated_content) : []) {
      scoped(item, id);
      const kind = normalizeContentKind(item.kind);
      const key = `${item.event_revision}:${kind}`;
      const previous = latest.get(key);
      if (
        !previous ||
        String(item.created_at ?? "") > String(previous.created_at ?? "")
      )
        latest.set(key, { ...item, kind });
    }
    const operations: Row[] =
      operationRaw === undefined
        ? []
        : rows(operationRaw).map((item) => {
            scoped(item, id);
            return {
              ...item,
              provider: String(item.kind).startsWith("calendar_")
                ? "Calendar"
                : String(item.kind).startsWith("gmail_")
                  ? "Gmail"
                  : "Unknown provider",
              approval_id:
                typeof item.approval_id === "string"
                  ? item.approval_id
                  : undefined,
              error_code: item.error_code ?? undefined,
              receipt: Object.keys(row(item.receipt ?? {})).length
                ? JSON.stringify(item.receipt)
                : undefined,
            };
          });
    const rsvps =
      rsvpRaw === undefined
        ? []
        : rows(rsvpRaw).map((item) => {
            scoped(item, id);
            // Keep observations and flag disagreements, without copying private notes into the UI model.
            const conflicts = rows(rsvpRaw).some(
              (other) =>
                other.invitee_id === item.invitee_id &&
                other.status !== item.status,
            );
            return {
              invitee_id: item.invitee_id,
              status: item.status,
              source: item.source,
              source_id: item.source_id,
              observed_at: item.observed_at,
              event_revision: item.event_revision,
              conflict: conflicts,
            };
          });
    const assets: Row[] = (review ? rows(review.artifacts) : []).map((item) => {
      scoped(item, id);
      const data = row(item.data);
      scoped(data, id);
      if (data.event_revision !== item.event_revision)
        throw new Error("Artifact revision mismatch.");
      return {
        ...data,
        id: item.id,
        state: data.review_state === "reviewed" ? "ready" : "needs_review",
        edit_url: undefined,
        preview_url: undefined,
        current_url: undefined,
      };
    });
    for (const raw of [flyerRaw, documentRaw]) {
      if (raw === undefined) continue;
      const current = scoped(row(raw), id);
      if (current.event_revision !== event.revision)
        throw new Error("The current artifact is stale.");
      const url = safeUrl(
        typeof current.url === "string" ? current.url : undefined,
      );
      if (!url) throw new Error("The server returned an unsafe artifact link.");
      const existing = assets.find(
        (asset) =>
          asset.kind === current.kind &&
          asset.event_revision === current.event_revision &&
          asset.sha256 === current.sha256,
      );
      const asset = {
        ...current,
        current_url: url,
        preview_url: current.kind === "flyer_png" ? url : undefined,
      };
      if (existing) Object.assign(existing, asset);
      else
        assets.push({
          ...asset,
          id: `${current.kind}:${current.event_revision}:${current.sha256}`,
          state: current.review_state === "reviewed" ? "ready" : "needs_review",
          edit_url: undefined,
        } as (typeof assets)[number]);
    }
    // A signed current artifact takes precedence over another export at the same revision.
    assets.sort(
      (a, b) => Number(Boolean(b.current_url)) - Number(Boolean(a.current_url)),
    );
    const facts = emptyFacts();
    const factRows = review ? rows(review.inclusion_facts) : [];
    for (const source of factRows) {
      scoped(source, id);
      if (source.revision !== event.revision) continue;
      const mappings = {
        step_free: "step_free",
        elevator: "elevator",
        captions: "captions",
      } as const;
      for (const [key, field] of Object.entries(mappings)) {
        const value = source[field];
        if (!["yes", "no", "unknown"].includes(String(value)))
          throw new Error("Invalid inclusion fact.");
        const reference = String(source.source ?? source.confirmed_by ?? "");
        const confirmed = String(source.confirmed_at ?? "").slice(0, 10);
        const sourced =
          reference.trim() && Number.isFinite(Date.parse(confirmed));
        facts[key as keyof typeof mappings] = {
          value:
            value === "unknown" || !sourced
              ? "unknown"
              : (value as "yes" | "no"),
          detail:
            value !== "unknown" && !sourced
              ? `Server reported ${value}; confirmation source/date is incomplete.`
              : "",
          source: reference,
          confirmed_on: confirmed,
        };
      }
      facts.diet.detail = String(source.diet_options ?? "");
      facts.observances.detail = String(source.observance_notes ?? "");
      // One combined field cannot establish separate loud-sound and strobe confirmations.
      facts.loud_sound.detail = facts.strobes.detail = String(
        source.loud_sound_strobes ?? "",
      );
    }
    const send = operations
      .filter((op) => op.kind === "gmail_send" && op.state === "succeeded")
      .at(-1);
    const work = queued.get(id);
    const content = [...latest.values()];
    const currentContent = content.filter(
      (item) => item.event_revision === event.revision,
    );
    warnings.push(
      "Preparation receipts are snapshots from this tab; live Go progress is unavailable. Inclusion findings and Gmail draft bindings are not available yet.",
    );
    const normalized = parseWorkspace({
      event,
      content,
      assets,
      operations,
      rsvps,
      facts,
      findings: [],
      work: work && work.event_revision === event.revision ? [work] : [],
      gmail: send ? { sent: true, event_revision: send.event_revision } : null,
      review_revision:
        currentContent.length &&
        currentContent.every((item) => item.state === "ready")
          ? event.revision
          : null,
    });
    return {
      ...normalized,
      live: {
        warnings,
        factsReadOnly: true,
        reviewAvailable: Boolean(review),
        receiptsAvailable: operationRaw !== undefined,
        rsvpsAvailable: rsvpRaw !== undefined,
        approval: (() => {
          const saved = approvals.get(`${id}:${event.revision}`);
          return saved &&
            normalized.content.some(
              (item) =>
                item.id === saved.invitation_content_id &&
                item.state === "ready" &&
                item.event_revision === event.revision,
            )
            ? saved
            : undefined;
        })(),
      },
    };
  }

  return {
    mode: "live",
    list: () => read.list(),
    get,
    async save(id, input, revision) {
      const payload = {
        title: input.title,
        description: input.description,
        location: input.location,
        starts_at: input.starts_at,
        ends_at: input.ends_at,
        timezone: input.timezone,
        organizer_contact: input.organizer_contact,
        links: input.links,
        invitees: input.invitees.map(({ email, display_name }) => ({
          email,
          ...(display_name ? { display_name } : {}),
        })),
        ...(id ? { expected_revision: revision } : {}),
      };
      const identity = JSON.stringify(payload);
      const key = creationKeys.get(identity) ?? crypto.randomUUID();
      if (!id) creationKeys.set(identity, key);
      const saved = parseEvent(
        await requestJson(
          id ? path(id) : "/api/events",
          token,
          id ? "PUT" : "POST",
          payload,
          id ? undefined : key,
        ),
      );
      if (id && saved.id !== id)
        throw new Error("The server returned a different saved event.");
      const result = await get(saved.id);
      if (!id) creationKeys.delete(identity);
      return result;
    },
    async prepare(id, revision) {
      const work = scoped(
        row(
          await requestJson(`${path(id)}/prepare`, token, "POST", {
            expected_revision: revision,
          }),
        ),
        id,
      );
      if (
        work.event_revision !== revision ||
        typeof work.id !== "string" ||
        !["queued", "awaiting_go", "running", "succeeded"].includes(
          String(work.state),
        )
      )
        throw new Error("Invalid preparation receipt.");
      queued.set(id, {
        id: work.id,
        event_revision: revision,
        state: work.state as "awaiting_go",
      });
      return get(id);
    },
    async review(id, revision, content, facts) {
      const original = await get(id);
      if (original.event.revision !== revision)
        throw new ApiError(
          "revision_conflict",
          "Reload the current revision before reviewing.",
        );
      if (JSON.stringify(facts) !== JSON.stringify(original.facts))
        throw new Error(
          "Inclusion answers cannot be saved by this API yet. Reload the server facts before reviewing writing.",
        );
      for (const item of content.filter((c) => c.event_revision === revision)) {
        const before = original.content.find((c) => c.id === item.id);
        if (!before)
          throw new Error("The writing changed. Reload before reviewing.");
        if (
          before.state === "ready" &&
          before.body === item.body &&
          before.subject === item.subject
        )
          continue;
        const changed =
          before.body !== item.body ||
          (before.subject ?? null) !== (item.subject ?? null);
        await requestJson(
          `/api/content/${encodeURIComponent(item.id)}/review`,
          token,
          "POST",
          {
            expected_revision: revision,
            ...(changed
              ? {
                  body: item.body,
                  ...(item.subject != null ? { subject: item.subject } : {}),
                }
              : {}),
          },
        );
      }
      return get(id);
    },
    async publish(id, revision, action, key, expectedContentId) {
      const cacheKey = `${id}:${revision}`;
      const existing = approvals.get(cacheKey);
      if (
        existing &&
        existing.invitation_content_id === expectedContentId &&
        existing.action === action
      )
        return get(id);
      const snapshot = await get(id);
      if (!snapshot.live?.reviewAvailable)
        throw new Error(
          "Load the writing review before approving distribution.",
        );
      if (snapshot.event.revision !== revision)
        throw new ApiError(
          "revision_conflict",
          "Reload before approving distribution.",
        );
      const mail = snapshot.content.find(
        (c) =>
          c.kind === (action === "update" ? "change_notice" : "invitation") &&
          c.event_revision === revision &&
          c.state === "ready",
      );
      if (!expectedContentId || mail?.id !== expectedContentId)
        throw new Error(
          "The invitation changed since your preview. Reload and review the new writing before approving.",
        );
      if (
        !mail ||
        !snapshot.live?.receiptsAvailable ||
        !["flyer", "document"].every((kind) =>
          snapshot.assets.some(
            (a) =>
              a.kind === kind &&
              a.event_revision === revision &&
              a.state === "ready" &&
              a.current_url,
          ),
        )
      )
        throw new Error(
          "Review current writing and both current assets, and load provider receipts before approving.",
        );
      // Approval endpoint has no idempotency contract. Reuse this tab's single attempt; never blindly retry an uncertain write.
      const requestKey = `${cacheKey}:${action}:${mail.id}`;
      void key; // REST approvals do not accept a client idempotency key.
      let pending = approvalRequests.get(requestKey);
      if (!pending) {
        pending = requestJson(`${path(id)}/approvals`, token, "POST", {
          expected_revision: revision,
          action,
          invitation_content_id: mail.id,
          acknowledged_unknowns: true,
        })
          .then((raw) => {
            const value = scoped(row(raw), id);
            if (
              typeof value.id !== "string" ||
              value.event_revision !== revision ||
              value.action !== action
            )
              throw new Error("Invalid approval receipt.");
            if (value.invitation_content_id !== mail.id)
              throw new Error(
                "Approval does not match the reviewed invitation.",
              );
            return {
              id: value.id,
              event_revision: revision,
              action,
              invitation_content_id: mail.id,
            };
          })
          .catch(() => {
            throw new Error(
              "Approval outcome could not be confirmed. Do not create another approval; ask the integration owner to check the stored approvals before retrying.",
            );
          });
        approvalRequests.set(requestKey, pending);
      }
      const approval = await pending;
      approvals.set(cacheKey, approval);
      return { ...snapshot, live: { ...snapshot.live!, approval } };
    },
  };
}
