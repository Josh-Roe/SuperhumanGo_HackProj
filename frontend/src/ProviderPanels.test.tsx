import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import {
  DistributionPreview,
  FlyerApproval,
  ProviderConnection,
} from "./ProviderPanels";

type Reply = [number, unknown];
/** Fake organizer server at the HTTP boundary: "METHOD path" → queued replies. */
function server(routes: Record<string, Reply[]>) {
  const fetcher = vi.fn(async (url: string, init: RequestInit) => {
    const key = `${init.method ?? "GET"} ${url}`;
    const queue = routes[key];
    if (!queue?.length)
      return new Response('{"detail":"Not Found"}', { status: 404 });
    const [status, body] = queue.length > 1 ? queue.shift()! : queue[0];
    return new Response(JSON.stringify(body), { status });
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
const bodyOf = (fetcher: ReturnType<typeof server>, key: string) =>
  fetcher.mock.calls
    .filter(([url, init]) => `${init.method ?? "GET"} ${url}` === key)
    .map(([, init]) => JSON.parse(String(init.body)));

const EVENT = "evt-1";
const DIGEST = "a".repeat(64);
const NEWER = "b".repeat(64);
const flyer = (stage: string, digest = DIGEST) => ({
  event_id: EVENT,
  event_revision: 3,
  stage,
  failure_code: null,
  generation_ids: {},
  job: null,
  design: {
    design_id: "D1",
    edit_url: "https://www.canva.com/design/D1/edit",
    view_url: null,
  },
  preview: {
    digest,
    expected: { title: "Garden picnic", location: "Community garden" },
    thumbnail_urls: ["https://document-export.canva.com/thumb-1.png"],
  },
  verified: null,
  export: null,
  asset: null,
  prior_attempts: 0,
});
const assets = (value: unknown) => ({
  prose: {},
  flyer: value,
  flyer_required_for_invitations: true,
  canva: "connected",
  storage: "configured",
});
const ASSETS = `GET /api/events/${EVENT}/assets`;

afterEach(() => window.history.replaceState(null, "", "/"));

it("connects Google by opening the server's authorization link with the organizer session", async () => {
  const fetcher = server({
    "GET /api/google/status": [[200, { connected: false, email: null }]],
    "POST /api/google/connect": [
      [
        200,
        {
          authorization_url:
            "https://accounts.google.com/o/oauth2/auth?state=s1",
        },
      ],
    ],
  });
  const navigate = vi.fn();
  const user = userEvent.setup();
  render(
    <ProviderConnection
      provider="google"
      accessToken="session-1"
      navigate={navigate}
    />,
  );
  expect(await screen.findByText("Not connected.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Connect Google" }));
  expect(navigate).toHaveBeenCalledWith(
    "https://accounts.google.com/o/oauth2/auth?state=s1",
  );
  expect(fetcher.mock.calls[1][1].headers).toMatchObject({
    Authorization: "Bearer session-1",
  });
});

it.each([
  ["google=connected", "status", /Google is connected/],
  [
    "google=error&reason=no_refresh_token",
    "alert",
    /did not grant offline access/,
  ],
  ["canva=error&reason=denied", "alert", /Canva access was not granted/],
])(
  "shows the %s callback result and removes the flag but keeps the event link",
  async (query, role, message) => {
    server({});
    window.history.replaceState(null, "", `/?event=${EVENT}&${query}`);
    render(<App />);
    expect(await screen.findByText(message)).toHaveAttribute("role", role);
    expect(window.location.search).toBe(`?event=${EVENT}`);
  },
);

it("approves the flyer with the exact digest of the preview on screen", async () => {
  const fetcher = server({
    [ASSETS]: [[200, assets(flyer("previewed"))]],
    [`POST /api/events/${EVENT}/assets/flyer/approve`]: [
      [200, flyer("approved")],
    ],
  });
  const user = userEvent.setup();
  render(
    <FlyerApproval eventId={EVENT} revision={3} accessToken="session-1" />,
  );
  expect(
    await screen.findByAltText("Canva flyer preview, page 1"),
  ).toBeVisible();
  expect(screen.getByText("Community garden")).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "Approve this exact preview" }),
  );
  expect(
    await screen.findByText(/Flyer approved for this revision/),
  ).toBeVisible();
  expect(
    bodyOf(fetcher, `POST /api/events/${EVENT}/assets/flyer/approve`),
  ).toEqual([{ expected_revision: 3, preview_digest: DIGEST }]);
  expect(
    screen.getByRole("button", { name: "Approve this exact preview" }),
  ).toBeDisabled();
});

it("refuses a stale approval and reloads the newer preview Go made meanwhile", async () => {
  server({
    [ASSETS]: [
      [200, assets(flyer("previewed"))],
      [200, assets(flyer("previewed", NEWER))],
    ],
    [`POST /api/events/${EVENT}/assets/flyer/approve`]: [
      [
        409,
        {
          detail: {
            code: "needs_review",
            message: "approval does not match the current preview",
          },
        },
      ],
    ],
  });
  const user = userEvent.setup();
  render(
    <FlyerApproval eventId={EVENT} revision={3} accessToken="session-1" />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Approve this exact preview" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "approval does not match the current preview",
  );
  expect(
    await screen.findByText(`Preview fingerprint ${NEWER.slice(0, 12)}`),
  ).toBeVisible();
});

it("abandons the flyer only after the organizer confirms", async () => {
  const fetcher = server({
    [ASSETS]: [[200, assets(flyer("created"))]],
    [`POST /api/events/${EVENT}/assets/flyer/abandon`]: [
      [200, { ...flyer("abandoned"), preview: null }],
    ],
  });
  const user = userEvent.setup();
  render(
    <FlyerApproval eventId={EVENT} revision={3} accessToken="session-1" />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Abandon flyer" }),
  );
  expect(
    bodyOf(fetcher, `POST /api/events/${EVENT}/assets/flyer/abandon`),
  ).toEqual([]);
  await user.click(
    screen.getByRole("button", { name: "Yes, send without a flyer" }),
  );
  expect(
    await screen.findByText(/You chose to send without a flyer/),
  ).toBeVisible();
  expect(
    bodyOf(fetcher, `POST /api/events/${EVENT}/assets/flyer/abandon`),
  ).toEqual([{ expected_revision: 3 }]);
});

it("lists the server's distribution blockers", async () => {
  server({
    [`GET /api/events/${EVENT}/distribution/preview`]: [
      [
        200,
        {
          event_id: EVENT,
          event_revision: 3,
          calendar_action: "update",
          calendar_event_id: "cal-1",
          gmail_action: "new_change_notice",
          required_content_kind: "change_notice",
          invitee_count: 0,
          blockers: [
            "needs_review: no invitees",
            "awaiting_go: no change_notice for revision 3",
          ],
        },
      ],
    ],
  });
  render(
    <DistributionPreview
      eventId={EVENT}
      revision={3}
      accessToken="session-1"
    />,
  );
  const blockers = await screen.findByRole("list", {
    name: "Distribution blockers",
  });
  expect(blockers).toHaveTextContent("needs review: no invitees");
  expect(blockers).toHaveTextContent(
    "awaiting go: no change_notice for revision 3",
  );
  expect(
    screen.getByText(/Update the existing Calendar event/),
  ).toHaveTextContent("cal-1");
});

it("says plainly when the server has no distribution preview route", async () => {
  server({});
  render(
    <DistributionPreview
      eventId={EVENT}
      revision={3}
      accessToken="session-1"
    />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    /does not show the distribution preview yet/,
  );
});

it("connects Canva through the browser-bound backend bootstrap", async () => {
  const url = `https://superhuman-go-event-backend.onrender.com/api/canva/start?state=${"s".repeat(43)}`;
  const fetcher = server({
    "GET /api/canva/status": [[200, { configured: true, connected: false }]],
    "POST /api/canva/connect": [[200, { authorization_url: url }]],
  });
  const navigate = vi.fn();
  render(
    <ProviderConnection
      provider="canva"
      accessToken="session-1"
      navigate={navigate}
    />,
  );
  await screen.findByText("Not connected.");
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Connect Canva" }));
  expect(navigate).toHaveBeenCalledWith(url);
  expect(fetcher.mock.calls[1][1].headers).toMatchObject({
    Authorization: "Bearer session-1",
  });
});

it.each([
  "https://evil.example/api/canva/start?state=" + "s".repeat(43),
  "https://superhuman-go-event-backend.onrender.com/api/canva/start?state=short",
  "https://superhuman-go-event-backend.onrender.com/api/canva/start?state=" +
    "s".repeat(43) +
    "&next=https://evil.example",
])("refuses an invalid Canva bootstrap URL: %s", async (url) => {
  server({
    "GET /api/canva/status": [[200, { connected: false }]],
    "POST /api/canva/connect": [[200, { authorization_url: url }]],
  });
  const navigate = vi.fn();
  render(
    <ProviderConnection
      provider="canva"
      accessToken="session-1"
      navigate={navigate}
    />,
  );
  await screen.findByText("Not connected.");
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Connect Canva" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "unsafe Canva connection link",
  );
  expect(navigate).not.toHaveBeenCalled();
});
