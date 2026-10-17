import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import App from "./App";
import { backend } from "./test/organizerBackend";

it("edits a live event, queues Go, reviews writing and records approval without claiming a send", async () => {
  const { gateway, event, fetcher } = await backend();
  const user = userEvent.setup();
  render(<App eventGateway={gateway} />);
  await user.click(
    await screen.findByRole("button", { name: /A neighborhood, together/ }),
  );
  const location = screen.getByLabelText("Location or online meeting link");
  await user.clear(location);
  await user.type(location, "Updated garden");
  await user.click(screen.getByRole("button", { name: "Save & continue" }));
  expect(
    await screen.findByText(/Server inclusion facts are read-only/),
  ).toBeVisible();
  const diet = screen.getByRole("group", { name: "Dietary options" });
  expect(within(diet).getByRole("combobox")).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Queue preparation" }));
  expect(
    await screen.findByText(/Awaiting Go. Open Superhuman Go/),
  ).toBeVisible();
  // This server has no newly generated writing for revision 2, so review/publish cannot pretend it exists.
  expect(
    screen.getByRole("button", { name: "Save review & continue" }),
  ).toBeDisabled();
  expect(
    fetcher.mock.calls.some(
      ([url, options]) =>
        url === `/api/events/${event.id}` && options.method === "PUT",
    ),
  ).toBe(true);
});

it("reviews stored Go prose and shows the exact durable approval for Go execution", async () => {
  const { gateway, fetcher } = await backend();
  const user = userEvent.setup();
  render(<App eventGateway={gateway} />);
  await user.click(
    await screen.findByRole("button", { name: /A neighborhood, together/ }),
  );
  await user.click(screen.getByRole("button", { name: /2Design & inclusion/ }));
  await user.click(
    screen.getByRole("checkbox", { name: /I reviewed this revision/ }),
  );
  await user.click(
    screen.getByRole("button", { name: "Save review & continue" }),
  );
  await screen.findByRole("heading", { name: "Your call to send." });
  const authorize = screen.getByRole("button", {
    name: "Confirm & authorize Go",
  });
  expect(authorize).toBeDisabled();
  await user.click(screen.getByRole("radio", { name: /First invitation/ }));
  await user.click(
    screen.getByRole("checkbox", { name: /I confirm the current event/ }),
  );
  await user.click(authorize);
  expect(
    await screen.findByRole("heading", {
      name: "Approval recorded. Awaiting Go.",
    }),
  ).toBeVisible();
  expect(
    (
      screen.getByLabelText(
        "Approved distribution prompt",
      ) as HTMLTextAreaElement
    ).value,
  ).toContain("approval-id");
  expect(
    screen.queryByText("Gmail send confirmed by provider receipt."),
  ).not.toBeInTheDocument();
  expect(
    fetcher.mock.calls.filter(([url]) => url.endsWith("/approvals")),
  ).toHaveLength(1);
});
