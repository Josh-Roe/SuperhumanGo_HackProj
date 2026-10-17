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

it("copies the key while masked and offers manual copying when clipboard access fails", async () => {
  const token = "go_" + "b".repeat(43);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    id: "synthetic-copy", token, expires_at: "2026-11-16T00:00:00Z",
  }))));
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  render(<GoConnector accessToken="synthetic-session" />);
  await user.click(screen.getByRole("button", { name: "Create Go key" }));
  const field = await screen.findByLabelText("Your Go key");
  await user.click(screen.getByRole("button", { name: "Copy key" }));
  expect(writeText).toHaveBeenCalledWith(token);
  expect(field).toHaveAttribute("type", "password");
  expect(screen.getByRole("status")).toHaveTextContent("Key copied");
  writeText.mockRejectedValueOnce(new Error("Clipboard blocked"));
  await user.click(screen.getByRole("button", { name: "Copy key" }));
  expect(field).toHaveAttribute("type", "text");
  expect(field).toHaveFocus();
  expect(screen.getByRole("status")).toHaveTextContent("Copy is blocked");
  await user.click(screen.getByRole("button", { name: "Mask key" }));
  expect(field).toHaveAttribute("type", "password");
  await user.click(screen.getByRole("button", { name: "Hide key" }));
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
