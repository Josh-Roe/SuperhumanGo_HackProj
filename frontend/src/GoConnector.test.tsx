import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { GoConnector } from "./GoConnector";

it("issues a personal token with the organizer session and keeps it masked and ephemeral", async () => {
  const token = "go_" + "a".repeat(43);
  const fetcher = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        id: "synthetic-connector",
        token,
        expires_at: "2026-11-16T00:00:00Z",
      }),
    ),
  );
  vi.stubGlobal("fetch", fetcher);
  const user = userEvent.setup();
  const view = render(<GoConnector accessToken="synthetic-session" />);
  await user.click(screen.getByRole("button", { name: "Create Go key" }));
  const field = await screen.findByLabelText("Your Go key");
  expect(field).toHaveValue(token);
  expect(field).toHaveFocus();
  expect(field).toHaveAttribute("type", "password");
  expect(fetcher.mock.calls[0][0]).toBe("/api/connectors");
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
    "Bearer synthetic-session",
  );
  await user.click(screen.getByRole("button", { name: "Hide key" }));
  expect(screen.queryByLabelText("Your Go key")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create Go key" })).toHaveFocus();
  view.unmount();
});
