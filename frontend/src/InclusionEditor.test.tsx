import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { InclusionEditor } from "./InclusionEditor";

const EVENT = "evt-1";
const URL_ = `/api/events/${EVENT}/inclusion`;
const ALL = ["christian", "jewish", "muslim", "hindu", "orthodox_christian"];
const unknown = { value: "unknown", source: null };
const source = {
  label: "Venue website",
  confirmed_by: "Organizer",
  observed_at: "2026-10-15T17:00:00Z",
  url: null,
};
function facts(over: object = {}) {
  return {
    step_free_entrance: unknown,
    above_ground_floor: unknown,
    elevator: unknown,
    food_served: unknown,
    diet_options: [],
    diet_source: null,
    required_diets: [],
    captions: unknown,
    loud_sound: unknown,
    strobes: unknown,
    observances_selected: false,
    observances: [],
    traditions: ALL,
    ...over,
  };
}
function view(version: number, f: object, findings: object[] = []) {
  return {
    event_id: EVENT,
    version,
    saved_at_event_revision: version ? 3 : null,
    updated_at: null,
    facts: f,
    review: {
      event_id: EVENT,
      event_revision: 3,
      audience: "organizer_private",
      requires_review: true,
      certification: false,
      findings,
    },
  };
}
const yomKippur = {
  category: "religious_observances",
  status: "attention",
  reason: "overlap_with_observance",
  sources: [],
  conflicts: ["Yom Kippur"],
  go_generation_id: null,
};

/** Fake inclusion endpoint: GET returns `gets` in order, PUT replies with `put`. */
function server(gets: object[], put: [number, object]) {
  const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
    if (init.method === "PUT")
      return new Response(JSON.stringify(put[1]), { status: put[0] });
    const body = gets.length > 1 ? gets.shift() : gets[0];
    return new Response(JSON.stringify(body));
  });
  vi.stubGlobal("fetch", fetcher);
  const puts = () =>
    fetcher.mock.calls
      .filter(([url, init]) => url === URL_ && init.method === "PUT")
      .map(([, init]) => JSON.parse(String(init.body)));
  return { puts };
}
const editor = () =>
  render(
    <InclusionEditor eventId={EVENT} revision={3} accessToken="session-1" />,
  );

it("saves a sourced fact in the server's form and shows the returned observance conflict", async () => {
  const { puts } = server(
    [view(0, facts())],
    [
      200,
      view(1, facts({ step_free_entrance: { value: "yes", source } }), [
        yomKippur,
      ]),
    ],
  );
  const user = userEvent.setup();
  editor();
  const entrance = await screen.findByRole("group", {
    name: "Step-free entrance",
  });
  expect(within(entrance).getByRole("combobox")).toHaveValue("unknown");
  await user.selectOptions(within(entrance).getByRole("combobox"), "yes");
  await user.click(
    screen.getByRole("button", { name: "Save inclusion facts" }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Step-free entrance: add a source",
  );
  expect(puts()).toEqual([]);

  await user.type(within(entrance).getByLabelText("Source"), "Venue website");
  await user.type(within(entrance).getByLabelText("Confirmed by"), "Organizer");
  await user.type(
    within(entrance).getByLabelText("Checked on"),
    "2026-10-15T10:00",
  );
  await user.click(
    screen.getByRole("button", { name: "Save inclusion facts" }),
  );

  expect(await screen.findByText("Overlaps: Yom Kippur")).toBeVisible();
  const [sent] = puts();
  expect(sent.expected_version).toBe(0);
  expect(sent.facts.step_free_entrance).toEqual({
    value: "yes",
    source: {
      label: "Venue website",
      confirmed_by: "Organizer",
      observed_at: new Date("2026-10-15T10:00").toISOString(),
      url: null,
    },
  });
  expect(sent.facts.loud_sound).toEqual(unknown);
  expect(sent.facts.strobes).toEqual(unknown);
  expect(sent.facts.traditions).toEqual(ALL);
});

it("opts out of holiday checks when every calendar is unchecked", async () => {
  const { puts } = server(
    [view(0, facts())],
    [200, view(1, facts({ traditions: [] }))],
  );
  const user = userEvent.setup();
  editor();
  const calendars = await screen.findByRole("group", {
    name: "Holiday calendars to check",
  });
  for (const box of within(calendars).getAllByRole("checkbox"))
    await user.click(box);
  expect(
    within(calendars).getByText(/No holiday calendars will be checked/),
  ).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "Save inclusion facts" }),
  );
  await screen.findByText(/Inclusion facts saved/);
  expect(puts()[0].facts.traditions).toEqual([]);
});

it("reloads the other session's facts when a save loses the version race", async () => {
  server(
    [view(0, facts()), view(1, facts({ captions: { value: "yes", source } }))],
    [409, { detail: { code: "revision_conflict", message: "stale version" } }],
  );
  const user = userEvent.setup();
  editor();
  await user.click(
    await screen.findByRole("button", { name: "Save inclusion facts" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Someone else saved these facts first",
  );
  const captions = screen.getByRole("group", {
    name: "Captions or live transcription",
  });
  expect(await within(captions).findByLabelText("Source")).toHaveValue(
    "Venue website",
  );
  expect(within(captions).getByRole("combobox")).toHaveValue("yes");
});
