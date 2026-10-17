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
const PKCE = "https://auth.example/auth/v1/token?grant_type=pkce";
const REFRESH = "https://auth.example/auth/v1/token?grant_type=refresh_token";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  history.replaceState(null, "", "/");
});

// Supabase answers the Google code exchange and refresh grants; the event API is the fake backend.
async function supabase(refresh: () => Response, { expiresIn = 3600 } = {}) {
  const { event, fetcher } = await backend();
  const original = fetcher.getMockImplementation()!;
  const refreshed: string[] = [];
  const bearers: string[] = [];
  fetcher.mockImplementation(async (url, options) => {
    if (url === "/api/config") return new Response(JSON.stringify(config));
    if (url === PKCE)
      return new Response(
        JSON.stringify({
          access_token: "first-access",
          refresh_token: "first-refresh",
          expires_in: expiresIn,
          user: { email: "organizer@example.com" },
        }),
      );
    if (url === REFRESH) {
      refreshed.push(JSON.parse(options.body).refresh_token);
      return refresh();
    }
    bearers.push(options?.headers?.Authorization);
    return original(url, options);
  });
  return { event, refreshed, bearers };
}
const renewed = () =>
  new Response(
    JSON.stringify({
      access_token: "second-access",
      refresh_token: "second-refresh",
      expires_in: 3600,
      user: { email: "organizer@example.com" },
    }),
  );
async function signInWithGoogle() {
  sessionStorage.setItem(
    "google-sign-in",
    JSON.stringify({ verifier: "v", config }),
  );
  history.replaceState(null, "", "/?code=google-code");
  const view = render(<App />);
  expect(await screen.findByText(/Signed in\./)).toBeVisible();
  return view;
}

it("keeps the organizer signed in after the page reloads", async () => {
  const { event, refreshed } = await supabase(renewed);
  const { unmount } = await signInWithGoogle();
  unmount();

  render(<App />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Your events" }));

  expect(await screen.findByText(event.title)).toBeVisible();
  expect(refreshed).toEqual(["first-refresh"]);
});

it("forgets the session when the organizer signs out", async () => {
  const { refreshed } = await supabase(renewed);
  const user = userEvent.setup();
  const { unmount } = await signInWithGoogle();
  await user.click(screen.getByRole("button", { name: "Settings" }));
  await user.click(screen.getByRole("button", { name: "Sign out" }));
  unmount();

  render(<App />);
  await user.click(screen.getByRole("button", { name: "Settings" }));

  expect(
    await screen.findByRole("button", { name: "Sign in with Google" }),
  ).toBeVisible();
  expect(refreshed).toEqual([]);
});

it("asks for sign-in again once Supabase rejects the saved session", async () => {
  const { refreshed } = await supabase(
    () => new Response("{}", { status: 400 }),
  );
  const { unmount } = await signInWithGoogle();
  unmount();
  const rejected = render(<App />);
  await vi.waitFor(() => expect(refreshed).toEqual(["first-refresh"]));
  rejected.unmount();

  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Settings" }));

  expect(
    await screen.findByRole("button", { name: "Sign in with Google" }),
  ).toBeVisible();
  expect(refreshed).toEqual(["first-refresh"]);
});

it("renews the access token before it expires without signing out", async () => {
  const { event, bearers, refreshed } = await supabase(renewed, {
    expiresIn: 61,
  });
  await signInWithGoogle();
  await vi.waitFor(() => expect(refreshed).toEqual(["first-refresh"]), {
    timeout: 3000,
  });
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Your events" }));
  await user.click(await screen.findByText(event.title));

  await vi.waitFor(() => expect(bearers.at(-1)).toBe("Bearer second-access"));
  expect(screen.queryByText(/You were signed out/)).toBeNull();
});
