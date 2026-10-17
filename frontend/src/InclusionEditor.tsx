import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  factKeys,
  loadInclusion,
  saveInclusion,
  traditions,
} from "./inclusion";
import type {
  FactKey,
  InclusionFacts,
  InclusionView,
  Source,
  Tradition,
  Value,
} from "./inclusion";
import { ProviderRequestError } from "./providers";

const labels: Record<FactKey, string> = {
  step_free_entrance: "Step-free entrance",
  above_ground_floor: "Event is off the ground floor",
  elevator: "Elevator to the event floor",
  food_served: "Food is served",
  captions: "Captions or live transcription",
  loud_sound: "Loud sound",
  strobes: "Strobe or flashing lights",
};
const categories: Record<string, string> = {
  plain_language: "Plain language",
  step_free_entrance: "Step-free entrance",
  elevator: "Elevator",
  captions: "Captions",
  loud_sound: "Loud sound",
  strobes: "Strobes",
  diet: "Food and diet",
  religious_observances: "Religious observances",
};
const words = (value: string) => value.replaceAll("_", " ");

interface SourceDraft {
  label: string;
  confirmed_by: string;
  observed: string; // <input type="datetime-local"> value, in the organizer's time zone
  url: string;
}
interface Draft {
  facts: Record<FactKey, { value: Value; source: SourceDraft }>;
  diet_options: string;
  diet_source: SourceDraft;
  traditions: Tradition[];
}

function toLocal(iso: string): string {
  const time = Date.parse(iso);
  if (!Number.isFinite(time)) return "";
  const d = new Date(time);
  return new Date(time - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
const sourceDraft = (s: Source | null): SourceDraft => ({
  label: s?.label ?? "",
  confirmed_by: s?.confirmed_by ?? "",
  observed: s ? toLocal(s.observed_at) : "",
  url: s?.url ?? "",
});
function toDraft(facts: InclusionFacts): Draft {
  return {
    facts: Object.fromEntries(
      factKeys.map((key) => [
        key,
        { value: facts[key].value, source: sourceDraft(facts[key].source) },
      ]),
    ) as Draft["facts"],
    diet_options: facts.diet_options.join(", "),
    diet_source: sourceDraft(facts.diet_source),
    traditions: facts.traditions,
  };
}
function toSource(s: SourceDraft): Source | null {
  const observed = Date.parse(s.observed);
  if (!s.label.trim() || !s.confirmed_by.trim() || !Number.isFinite(observed))
    return null;
  return {
    label: s.label.trim(),
    confirmed_by: s.confirmed_by.trim(),
    observed_at: new Date(observed).toISOString(),
    url: s.url.trim() || null,
  };
}
/** Builds the server form, or returns the reason it cannot be saved. */
function toFacts(draft: Draft, base: InclusionFacts): InclusionFacts | string {
  const facts = { ...base };
  for (const key of factKeys) {
    const { value, source } = draft.facts[key];
    const sourced = value === "unknown" ? null : toSource(source);
    if (value !== "unknown" && !sourced)
      return `${labels[key]}: add a source, who confirmed it and when, or keep it unknown.`;
    facts[key] = { value, source: sourced };
  }
  const options = draft.diet_options
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);
  const dietSource = toSource(draft.diet_source);
  if (options.length && !dietSource)
    return "Dietary options: add a source, who confirmed them and when, or leave the list empty.";
  if (
    draft.diet_source.url.trim() &&
    !/^https?:\/\//.test(draft.diet_source.url.trim())
  )
    return "Dietary options: the source link must start with http:// or https://.";
  for (const key of factKeys) {
    const url = draft.facts[key].source.url.trim();
    if (
      draft.facts[key].value !== "unknown" &&
      url &&
      !/^https?:\/\//.test(url)
    )
      return `${labels[key]}: the source link must start with http:// or https://.`;
  }
  return {
    ...facts,
    diet_options: options,
    diet_source: options.length ? dietSource : null,
    traditions: draft.traditions,
  };
}

function SourceFields({
  value,
  onChange,
}: {
  value: SourceDraft;
  onChange: (next: SourceDraft) => void;
}) {
  const field = (key: keyof SourceDraft) => ({
    value: value[key],
    onChange: (e: { target: { value: string } }) =>
      onChange({ ...value, [key]: e.target.value }),
  });
  return (
    <div className="source-fields">
      <label>
        Source
        <input
          placeholder="Venue website, site visit, caterer menu…"
          {...field("label")}
        />
      </label>
      <label>
        Confirmed by
        <input {...field("confirmed_by")} />
      </label>
      <label>
        Checked on
        <input type="datetime-local" {...field("observed")} />
      </label>
      <label>
        Link (optional)
        <input type="url" {...field("url")} />
      </label>
    </div>
  );
}

export function InclusionEditor({
  eventId,
  revision,
  accessToken,
}: {
  eventId: string;
  revision: number;
  accessToken: string;
}) {
  const [view, setView] = useState<InclusionView>();
  const [draft, setDraft] = useState<Draft>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reloads, setReloads] = useState(0);
  useEffect(() => {
    let active = true;
    loadInclusion(eventId, accessToken).then(
      (value) => {
        if (!active) return;
        setView(value);
        setDraft(toDraft(value.facts));
      },
      (err) =>
        active &&
        setError(
          err instanceof Error
            ? err.message
            : "Inclusion facts could not be loaded.",
        ),
    );
    return () => {
      active = false;
    };
  }, [eventId, accessToken, reloads]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!view || !draft) return;
    setError("");
    setMessage("");
    const facts = toFacts(draft, view.facts);
    if (typeof facts === "string") {
      setError(facts);
      return;
    }
    setBusy(true);
    try {
      const saved = await saveInclusion(
        eventId,
        view.version,
        facts,
        accessToken,
      );
      setView(saved);
      setDraft(toDraft(saved.facts));
      setMessage("Inclusion facts saved. The findings below are rechecked.");
    } catch (err) {
      if (
        err instanceof ProviderRequestError &&
        err.code === "revision_conflict"
      ) {
        setError(
          "Someone else saved these facts first. The latest saved facts are loaded; re-apply your changes.",
        );
        setReloads((n) => n + 1);
      } else
        setError(
          err instanceof Error
            ? err.message
            : "Inclusion facts could not be saved.",
        );
    } finally {
      setBusy(false);
    }
  }

  const setFact = (key: FactKey, next: Partial<Draft["facts"][FactKey]>) =>
    setDraft(
      (d) =>
        d && {
          ...d,
          facts: { ...d.facts, [key]: { ...d.facts[key], ...next } },
        },
    );

  return (
    <section className="panel" aria-labelledby="inclusion-editor">
      <h2 id="inclusion-editor">A quick inclusion check.</h2>
      <p className="muted">
        Record only what you have confirmed, with its source and date. Anything
        else stays unknown.
      </p>
      {!view && !error && <p role="status">Loading inclusion facts…</p>}
      {view &&
        view.saved_at_event_revision !== null &&
        view.saved_at_event_revision !== revision && (
          <p className="notice">
            These facts were saved for revision {view.saved_at_event_revision};
            the event is now at revision {revision}. Re-confirm venue facts if
            the place or time changed, then save.
          </p>
        )}
      {view && view.review_revision !== revision && (
        <p className="notice">
          The findings below were checked against revision{" "}
          {view.review_revision}.{" "}
          <button
            type="button"
            className="text-button"
            onClick={() => setReloads((n) => n + 1)}
          >
            Recheck for revision {revision}
          </button>
        </p>
      )}
      {draft && (
        <form onSubmit={save}>
          <div className="fact-grid">
            {factKeys.map((key) => (
              <fieldset className="fact" key={key} disabled={busy}>
                <legend>{labels[key]}</legend>
                <label>
                  What do you know?
                  <select
                    value={draft.facts[key].value}
                    onChange={(e) =>
                      setFact(key, { value: e.target.value as Value })
                    }
                  >
                    <option value="unknown">Unknown / not checked</option>
                    <option value="yes">Yes · confirmed</option>
                    <option value="no">No · confirmed</option>
                  </select>
                </label>
                {draft.facts[key].value !== "unknown" && (
                  <SourceFields
                    value={draft.facts[key].source}
                    onChange={(source) => setFact(key, { source })}
                  />
                )}
                {view &&
                  view.facts[key].value !== "unknown" &&
                  !view.facts[key].source && (
                    <p className="small">
                      Saved as {view.facts[key].value} without a source, so the
                      check treats it as unknown.
                    </p>
                  )}
              </fieldset>
            ))}
            <fieldset className="fact" disabled={busy}>
              <legend>Dietary options</legend>
              <label>
                Options offered (comma-separated)
                <input
                  value={draft.diet_options}
                  onChange={(e) =>
                    setDraft((d) => d && { ...d, diet_options: e.target.value })
                  }
                />
              </label>
              {draft.diet_options.trim() && (
                <SourceFields
                  value={draft.diet_source}
                  onChange={(diet_source) =>
                    setDraft((d) => d && { ...d, diet_source })
                  }
                />
              )}
              <p className="small muted">
                Guests’ own dietary needs stay private and never go into
                invitations.
              </p>
            </fieldset>
            <fieldset className="fact" disabled={busy}>
              <legend>Holiday calendars to check</legend>
              {traditions.map(([key, name]) => (
                <label key={key} className="check">
                  <input
                    type="checkbox"
                    checked={draft.traditions.includes(key)}
                    onChange={(e) =>
                      setDraft(
                        (d) =>
                          d && {
                            ...d,
                            traditions: e.target.checked
                              ? traditions
                                  .map(([k]) => k)
                                  .filter(
                                    (k) =>
                                      k === key || d.traditions.includes(k),
                                  )
                              : d.traditions.filter((k) => k !== key),
                          },
                      )
                    }
                  />
                  {name}
                </label>
              ))}
              {draft.traditions.length === 0 && (
                <p className="small">
                  No holiday calendars will be checked. Religious-observance
                  conflicts will not be flagged.
                </p>
              )}
            </fieldset>
          </div>
          <button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save inclusion facts"}
          </button>
        </form>
      )}
      <p role="status">{message}</p>
      {error && <p role="alert">{error}</p>}
      {view && (
        <>
          <h3>What the check found</h3>
          <ul className="findings" aria-label="Inclusion findings">
            {view.findings.map((f) => (
              <li className="finding" key={f.category}>
                <strong>{categories[f.category] ?? words(f.category)}</strong> ·{" "}
                {words(f.status)}
                <p>{words(f.reason)}</p>
                {f.conflicts.length > 0 && (
                  <p>Overlaps: {f.conflicts.join(", ")}</p>
                )}
                {f.sources.map((s) => (
                  <p className="small" key={`${s.label}:${s.observed_at}`}>
                    {s.label} · {s.confirmed_by} · {s.observed_at.slice(0, 10)}
                  </p>
                ))}
              </li>
            ))}
          </ul>
          <p className="small muted">
            This review does not certify the venue. Private guest needs stay out
            of shared invitations.
          </p>
        </>
      )}
    </section>
  );
}
