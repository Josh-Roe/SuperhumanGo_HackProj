import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { backend } from "./test/organizerBackend";

const config = {
  configured: true,
  supabase_url: "https://auth.example",
  supabase_publishable_key: "public",
};

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  history.replaceState(null, "", "/");
});

it("signs in with Google and connects the organizer workspace on return", async () => {
  const { event, fetcher } = await backend();
  const original = fetcher.getMockImplementation()!;
  let exchanged: Record<string, string> | undefined;
  fetcher.mockImplementation(async (url, options) => {
    if (url === "/api/config") return new Response(JSON.stringify(config));
    if (url === "https://auth.example/auth/v1/token?grant_type=pkce") {
      exchanged = JSON.parse(options.body);
      return new Response(
        JSON.stringify({
          access_token: "synthetic-session",
          expires_in: 3600,
          user: { email: "organizer@example.com" },
        }),
      );
    }
    return original(url, options);
  });
  const assign = vi.fn();
  vi.spyOn(window, "location", "get").mockReturnValue({
    ...window.location,
    assign,
  });
  const user = userEvent.setup();
  const { unmount } = render(<App />);
  await user.click(screen.getByRole("button", { name: "Settings" }));
  await user.click(screen.getByRole("button", { name: "Sign in with Google" }));
  await vi.waitFor(() => expect(assign).toHaveBeenCalledOnce());
  const authorize = new URL(assign.mock.calls[0][0]);
  expect(authorize.origin + authorize.pathname).toBe(
    "https://auth.example/auth/v1/authorize",
  );
  expect(authorize.searchParams.get("provider")).toBe("google");
  unmount();
  vi.restoreAllMocks();

  history.replaceState(null, "", "/?code=google-code");
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Your events" }));
  expect(await screen.findByText(event.title)).toBeVisible();
  expect(screen.getByText("You’re signed in as organizer@example.com.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Create Go key" })).toBeVisible();
  expect(exchanged?.auth_code).toBe("google-code");
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(exchanged!.code_verifier),
  );
  const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
  expect(authorize.searchParams.get("code_challenge")).toBe(challenge);
  expect(location.search).toBe("");
});

it("offers Google sign-in on the events page without visiting Settings", async () => {
  const { fetcher } = await backend();
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation(async (url, options) =>
    url === "/api/config"
      ? new Response(JSON.stringify(config))
      : original(url, options),
  );
  const assign = vi.fn();
  vi.spyOn(window, "location", "get").mockReturnValue({
    ...window.location,
    assign,
  });
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Sign in with Google" }));
  await vi.waitFor(() => expect(assign).toHaveBeenCalledOnce());
  expect(new URL(assign.mock.calls[0][0]).searchParams.get("provider")).toBe(
    "google",
  );
});

it("reports a denied Google sign-in without exchanging a code", async () => {
  const { fetcher } = await backend();
  sessionStorage.setItem(
    "google-sign-in",
    JSON.stringify({ verifier: "v", config }),
  );
  history.replaceState(null, "", "/?error=access_denied");
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Google sign-in did not finish: access_denied.",
  );
  expect(fetcher).not.toHaveBeenCalled();
  expect(sessionStorage.getItem("google-sign-in")).toBeNull();
});
