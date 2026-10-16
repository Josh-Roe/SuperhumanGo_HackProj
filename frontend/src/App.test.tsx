import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
async function workspace() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("button", { name: /A neighborhood, together/ });
  return user;
}
async function sample() {
  const user = await workspace();
  await user.click(
    screen.getByRole("button", { name: /A neighborhood, together/ }),
  );
  await screen.findByRole("button", { name: "Save & continue" });
  return user;
}
describe("simplified event workspace", () => {
  it("opens directly to events with only the three requested sidebar destinations", async () => {
    await workspace();
    expect(screen.getByRole("heading", { name: "Your events" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Sign in" }),
    ).not.toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    expect(
      within(nav)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["▦Your events", "⚙Settings", "○Profile"]);
    expect(screen.getByRole("button", { name: "Add event" })).toBeVisible();
    expect(
      screen.queryByText("A little planning. A great gathering."),
    ).not.toBeInTheDocument();
  });
  it("keeps the three creation stages inside an event and opens Go at its official URL", async () => {
    const user = await sample();
    const flow = screen.getByRole("navigation", { name: "Event creation" });
    expect(within(flow).getAllByRole("button")).toHaveLength(3);
    await user.click(
      screen.getByRole("button", { name: /2Design & inclusion/ }),
    );
    expect(
      screen.getByRole("link", { name: /Continue in Superhuman Go/ }),
    ).toHaveAttribute("href", "https://go.superhuman.com/");
    expect(
      screen.getByRole("link", { name: /Connect Canva in Go/ }),
    ).toHaveAttribute("href", "https://go.superhuman.com/");
    await user.click(
      screen.getByText("Connect the custom MCP & get your prompt"),
    );
    expect(
      (screen.getByLabelText("Prompt for Go") as HTMLTextAreaElement).value,
    ).toContain("preview-gathering");
    expect(
      screen.getByText(/hosted MCP address is awaiting setup/),
    ).toBeVisible();
    expect(screen.getByText(/does not install the connector/)).toBeVisible();
  });
  it("adds an event and advances through design to distribution without making up Go output", async () => {
    const user = await workspace();
    await user.click(screen.getByRole("button", { name: "Add event" }));
    await user.click(
      screen.getByRole("button", {
        name: "Enter event details manually instead",
      }),
    );
    expect(
      screen.getByRole("button", { name: /2Design & inclusion/ }),
    ).toBeDisabled();
    await user.type(screen.getByLabelText("Event title"), "Garden meetup");
    await user.type(
      screen.getByLabelText("Location or online meeting link"),
      "Community garden",
    );
    await user.type(
      screen.getByLabelText("Organizer email"),
      "organizer@example.com",
    );
    await user.type(screen.getByLabelText("Start time"), "2026-11-07T10:00");
    await user.type(screen.getByLabelText("End time"), "2026-11-07T12:00");
    await user.click(screen.getByRole("button", { name: "Save & continue" }));
    expect(
      await screen.findByText(/Waiting for Go’s first draft/),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /2Design & inclusion/ }),
    ).toHaveAttribute("aria-current", "step");
    await user.click(screen.getByRole("button", { name: "Queue preparation" }));
    expect(
      await screen.findByText(/Awaiting Go. Open Superhuman Go/),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Preview distribution" }),
    );
    expect(
      screen.getByRole("button", { name: "Confirm & publish" }),
    ).toBeDisabled();
    await user.click(
      within(screen.getByRole("navigation", { name: "Workspace" })).getByRole(
        "button",
        { name: "Your events" },
      ),
    );
    expect(
      await screen.findByRole("button", { name: /Garden meetup/ }),
    ).toBeVisible();
  });
  it("edits writing with provenance and requires explicit review", async () => {
    const user = await sample();
    await user.click(
      screen.getByRole("button", { name: /2Design & inclusion/ }),
    );
    await user.click(
      screen.getByText("Event description", { selector: "summary" }),
    );
    const editor = screen.getByLabelText(/Event description.*Superhuman Go/s);
    await user.type(editor, " Bring a notebook.");
    expect(screen.getByText("Edited by organizer · revision 2")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Save review & continue" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", { name: /I reviewed this revision/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Save review & continue" }),
    );
    expect(
      await screen.findByText("Review saved for this revision."),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Confirm & publish" }),
    ).toBeDisabled();
  });
  it("retains holiday and diet questions and blocks unsourced accessibility claims", async () => {
    const user = await sample();
    await user.click(
      screen.getByRole("button", { name: /2Design & inclusion/ }),
    );
    expect(
      screen.getByLabelText("Which holidays or observances should Go check?"),
    ).toBeVisible();
    expect(
      screen.getByLabelText(
        "Is food served? Which dietary options are confirmed?",
      ),
    ).toBeVisible();
    await user.click(screen.getByText("Access, captions & sensory details"));
    const fact = screen.getByRole("group", { name: "Step-free entrance" });
    await user.selectOptions(within(fact).getByRole("combobox"), "yes");
    await user.click(
      screen.getByRole("checkbox", { name: /I reviewed this revision/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Save review & continue" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Add a source and confirmation date",
    );
  });
  it("keeps provider failures and private RSVP evidence available within distribution", async () => {
    const user = await sample();
    await user.click(screen.getByRole("button", { name: /3Distribution/ }));
    expect(screen.getByText(/Your invitation is unsent/)).toBeVisible();
    await user.click(screen.getByText("Provider status & revisions"));
    expect(screen.getByText("integration not connected")).toBeVisible();
    await user.click(screen.getByText("Guest responses"));
    expect(screen.getByText("Conflict · needs review")).toBeVisible();
    expect(screen.getByRole("table")).toHaveAccessibleName(
      "Invited people and response evidence",
    );
  });
  it("provides Go setup in settings and saves a local profile without sign-up", async () => {
    const user = await workspace();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByText("Your connected tools")).toBeVisible();
    expect(screen.getAllByRole("link", { name: /Connect in Go/ })).toHaveLength(
      3,
    );
    expect(screen.getByLabelText("Prompt for Go")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Profile" }));
    await user.clear(screen.getByLabelText("Your name"));
    await user.type(screen.getByLabelText("Your name"), "Alex");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Profile saved in this tab.",
    );
    expect(screen.getByText("Alex")).toBeVisible();
  });
  it("handles a backend error in settings without claiming Go is connected", async () => {
    const user = await workspace();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByText("Workspace connection status"));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await user.click(screen.getByRole("button", { name: "Check connection" }));
    expect(
      await screen.findByText("Backend unavailable. Try again."),
    ).toBeVisible();
  });
});

describe("Go-backed event read model", () => {
  it("fills event fields and routes design and email content to their named groups on refresh", async () => {
    const { createPreviewGateway } = await import("./preview");
    const { parseWorkspace } = await import("./api");
    const base = createPreviewGateway();
    const snapshot = await base.get("preview-gathering");
    const incoming = parseWorkspace({
      ...snapshot,
      event: {
        ...snapshot.event,
        title: "Community picnic",
        location: "Lakeside garden",
      },
      content: [
        {
          id: "design-output",
          kind: "flyer_brief",
          body: "Blue and yellow. Hand-drawn lemons. Date prominently at the top.",
          producer: "superhuman_go",
          event_revision: 2,
          state: "needs_review",
        },
        {
          id: "email-output",
          kind: "invitation",
          body: "Bring a picnic blanket.",
          subject: "Join our community picnic",
          producer: "superhuman_go",
          event_revision: 2,
          state: "needs_review",
        },
      ],
    });
    const gateway = {
      ...base,
      list: vi.fn().mockResolvedValue([incoming.event]),
      get: vi.fn().mockResolvedValue(incoming),
    };
    const user = userEvent.setup();
    render(<App eventGateway={gateway} />);
    await user.click(
      await screen.findByRole("button", { name: /Community picnic/ }),
    );
    expect(screen.getByLabelText("Event title")).toHaveValue(
      "Community picnic",
    );
    expect(
      screen.getByLabelText("Location or online meeting link"),
    ).toHaveValue("Lakeside garden");
    await user.click(
      screen.getByRole("button", { name: /2Design & inclusion/ }),
    );
    const design = screen.getByRole("group", {
      name: "Go output: Canva design",
    });
    await user.click(
      within(design).getByText("Canva design instructions", {
        selector: "summary",
      }),
    );
    expect(within(design).getByRole("textbox")).toHaveValue(
      "Blue and yellow. Hand-drawn lemons. Date prominently at the top.",
    );
    const mail = screen.getByRole("group", { name: "Go output: Distribution" });
    await user.click(
      within(mail).getByText("Invitation", { selector: "summary" }),
    );
    expect(within(mail).getByLabelText("Email subject")).toHaveValue(
      "Join our community picnic",
    );
    await user.click(screen.getByRole("button", { name: "↻ Refresh" }));
    expect(gateway.get).toHaveBeenCalledTimes(2);
  });
});

describe("Go-first event transfer test", () => {
  it("starts new events in Go without first creating a placeholder event", async () => {
    const user = await workspace();
    await user.click(screen.getByRole("button", { name: "Add event" }));
    expect(
      screen.getByRole("heading", { name: "Start your event with Go" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Continue in Superhuman Go/ }),
    ).toHaveAttribute("href", "https://go.superhuman.com/");
    expect(screen.queryByLabelText("Event title")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Check Your events" }),
    ).toBeDisabled();
    expect(screen.getByText(/Go cannot write to this tab/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "← Your events" }));
    expect(
      screen.getAllByRole("button", { name: /A neighborhood, together/ }),
    ).toHaveLength(1);
  });
  it("reads Go-created canonical records from a connected gateway and exposes their exact ID", async () => {
    const { createPreviewGateway } = await import("./preview");
    const { createEventTransferGateway } = await import("./api");
    const snapshot = await createPreviewGateway().get("preview-gathering");
    const event = {
      ...snapshot.event,
      id: "go-saved-event",
      title: "Go transfer test 01",
      location: "Synthetic garden",
    };
    let saved = false;
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation((path: string) =>
          Promise.resolve(
            new Response(
              JSON.stringify(
                path.startsWith("/api/events?")
                  ? saved
                    ? [event]
                    : []
                  : event,
              ),
            ),
          ),
        ),
    );
    const user = userEvent.setup();
    render(
      <App eventGateway={createEventTransferGateway("synthetic-user-jwt")} />,
    );
    await user.click(screen.getByRole("button", { name: "Add event" }));
    saved = true;
    await user.click(screen.getByRole("button", { name: "Check Your events" }));
    await user.click(
      await screen.findByRole("button", { name: /Go transfer test 01/ }),
    );
    expect(screen.getByText("go-saved-event")).toBeVisible();
    expect(screen.getByLabelText("Event title")).toHaveValue(
      "Go transfer test 01",
    );
    expect(
      screen.getByLabelText("Location or online meeting link"),
    ).toHaveValue("Synthetic garden");
    expect(
      screen.getByRole("button", { name: "Read-only event" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /2Design & inclusion/ }),
    ).toBeDisabled();
    expect(screen.getByText(/Connected event-details test/)).toBeVisible();
  });
});

describe("event API readiness", () => {
  it("checks registration before requesting account credentials", async () => {
    const user = await workspace();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.queryByLabelText("Account password")).not.toBeInTheDocument();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 404 })),
    );
    await user.click(screen.getByRole("button", { name: "Check event API" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "not registered",
    );
    expect(screen.queryByLabelText("Account password")).not.toBeInTheDocument();
  });
});
