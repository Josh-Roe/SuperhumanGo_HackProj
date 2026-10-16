import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
async function preview() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: /Open local preview/ }));
  await screen.findByRole("button", { name: /A neighborhood, together/ });
  return user;
}
async function sample() {
  const user = await preview();
  await user.click(
    screen.getByRole("button", { name: /A neighborhood, together/ }),
  );
  await screen.findByRole("button", { name: "Save & continue" });
  return user;
}
describe("organizer workspace", () => {
  it("keeps sign-in distinct from the synthetic, non-publishing preview", async () => {
    const user = await preview();
    expect(
      screen.getByText(/Synthetic sample writing and receipts/),
    ).toBeVisible();
    expect(screen.getByText(/MCP event creation is awaiting/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Leave preview/ }));
    expect(screen.getByRole("heading", { name: "Welcome in." })).toBeVisible();
  });
  it("offers keyboard navigation, private RSVP evidence, and partial provider states", async () => {
    const user = await sample();
    await user.click(screen.getByRole("button", { name: /Updates & sync/ }));
    expect(
      screen.getByText("Unsent draft · update existing draft"),
    ).toBeVisible();
    expect(screen.getAllByText("Stale").length).toBeGreaterThan(0);
    expect(screen.getByText("integration not connected")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /RSVPs/ }));
    expect(screen.getByText("Conflict · needs review")).toBeVisible();
    expect(
      screen.getByText(
        /Private dietary and accessibility details are excluded/,
      ),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "RSVPs" })).toHaveFocus();
    expect(screen.getByRole("table")).toHaveAccessibleName(
      "Invited people and response evidence",
    );
  });
  it("saves manual events, then waits truthfully for Go without inventing content", async () => {
    const user = await preview();
    await user.click(screen.getByRole("button", { name: /Create manually/ }));
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
      await screen.findByText("Waiting for Go’s first draft"),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Request preparation" }),
    );
    expect(
      await screen.findByText(/Awaiting Go. Ask your Go agent/),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Distribution/ }));
    expect(
      screen.getByRole("button", { name: "Confirm & publish" }),
    ).toBeDisabled();
  });
  it("edits Go previews with provenance and records explicit review without sending", async () => {
    const user = await sample();
    await user.click(
      screen.getByRole("button", { name: /Design & inclusion/ }),
    );
    const editor = screen.getByLabelText(
      /Event description.*needs review.*Superhuman Go/s,
    );
    await user.type(editor, " Please bring a notebook.");
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
    expect(
      screen.getByText(/Local preview: publish is disabled/),
    ).toBeVisible();
  });
  it("blocks unsourced inclusion claims and preserves unknown options", async () => {
    const user = await sample();
    await user.click(
      screen.getByRole("button", { name: /Design & inclusion/ }),
    );
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
  it("refreshes the existing real health contract and handles backend failure", async () => {
    const user = await preview();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await user.click(
      screen.getByRole("button", { name: "Backend not checked" }),
    );
    expect(
      await screen.findByRole("button", {
        name: "Backend unavailable · retry connection",
      }),
    ).toBeVisible();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation((path: string) =>
          Promise.resolve(
            new Response(
              JSON.stringify(
                path === "/api/health"
                  ? { status: "ok", service: "backend" }
                  : {
                      superhuman: {
                        transport: "mcp",
                        configured: true,
                        verified: false,
                        endpoint: "/mcp",
                      },
                      model: { configured: false, runtime: "not_configured" },
                    },
              ),
            ),
          ),
        ),
    );
    await user.click(
      screen.getByRole("button", {
        name: "Backend unavailable · retry connection",
      }),
    );
    expect(
      await screen.findByRole("button", {
        name: /Backend online · MCP configured · Go unverified/,
      }),
    ).toBeVisible();
  });
});
