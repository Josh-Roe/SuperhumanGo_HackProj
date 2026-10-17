import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import App from "./App";
import { ApiError } from "./api";
import { backend } from "./test/organizerBackend";

it("opens a linked event after connection or on authenticated load, and hides missing/foreign IDs", async () => {
  const previousUrl = location.href;
  try {
    const { event, gateway, fetcher } = await backend();
    history.replaceState(null, "", `/?event=${event.id}`);
    const original = fetcher.getMockImplementation()!;
    fetcher.mockImplementation(async (url, options) => {
      if (url === "/api/config")
        return new Response(
          JSON.stringify({
            configured: true,
            supabase_url: "https://auth.example",
            supabase_publishable_key: "public",
          }),
        );
      if (url.startsWith("https://auth.example/auth/"))
        return new Response(
          JSON.stringify({
            access_token: "synthetic-session",
            expires_in: 3600,
            user: { email: "organizer@example.com" },
          }),
        );
      return original(url, options);
    });
    const user = userEvent.setup();
    render(<App />);
    expect(fetcher).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Connect to open event" }),
    );
    await user.click(screen.getByRole("button", { name: "Check event API" }));
    await user.type(
      await screen.findByLabelText("Organizer account email"),
      "organizer@example.com",
    );
    await user.type(
      screen.getByLabelText("Account password"),
      "synthetic-password",
    );
    await user.click(
      screen.getByRole("button", { name: "Connect existing workspace" }),
    );
    expect(await screen.findByLabelText("Event title")).toHaveValue(
      event.title,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: event.title }),
    ).toBeVisible();
    cleanup();
    render(<App eventGateway={gateway} />);
    expect(await screen.findByLabelText("Event title")).toHaveValue(
      event.title,
    );
    cleanup();
    for (const code of ["api_unavailable", "forbidden"]) {
      history.replaceState(null, "", "/?event=unavailable-event");
      render(
        <App
          eventGateway={{
            ...gateway,
            get: async () => {
              throw new ApiError(code, "private server detail");
            },
          }}
        />,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Event not found.",
      );
      expect(
        screen.queryByText("private server detail"),
      ).not.toBeInTheDocument();
      cleanup();
    }
  } finally {
    history.replaceState(null, "", previousUrl);
  }
});
