import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

const projectStatus = {
  superhuman: {
    transport: "mcp",
    configured: true,
    verified: false,
    endpoint: "/mcp",
  },
  model: { configured: false, runtime: "not_configured" },
};

function mockBackend() {
  return vi
    .fn()
    .mockImplementation((path: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path === "/api/health"
              ? { status: "ok", service: "backend" }
              : projectStatus,
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
}

describe("workspace readiness", () => {
  it("uses the real API contract and distinguishes configured credentials from verification", async () => {
    const fetchMock = mockBackend();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking the Python backend",
    );
    expect(
      await screen.findByText("Backend connected · Health check passed"),
    ).toBeVisible();
    expect(screen.getByText("Credentials configured")).toBeVisible();
    expect(
      screen.getByText(
        /A live Superhuman connection has not yet been verified/,
      ),
    ).toBeVisible();
    expect(screen.getByText("No model configured")).toBeVisible();
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/health",
      "/api/status",
    ]);
  });

  it("lets the user recover after a failed backend request", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    render(<App />);
    expect(await screen.findByText(/Backend unavailable/)).toBeVisible();
    expect(
      screen.queryByText("Credentials configured"),
    ).not.toBeInTheDocument();
    vi.stubGlobal("fetch", mockBackend());
    await user.click(screen.getByRole("button", { name: /Refresh status/ }));
    expect(
      await screen.findByText("Backend connected · Health check passed"),
    ).toBeVisible();
  });

  it("rejects incompatible or malformed backend responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(() =>
          Promise.resolve(new Response("{}", { status: 200 })),
        ),
    );
    render(<App />);
    expect(
      await screen.findByText(/health response did not match the API contract/),
    ).toBeVisible();
  });
});
