import assert from "node:assert/strict";
import test from "node:test";
import * as sdk from "@codahq/packs-sdk";
import { callDraftTool, registerDraftActions } from "./draft-actions.ts";

const endpoint = "https://synthetic.example/mcp";
test("typed draft actions retain approval and call canonical MCP without credentials or sends", async () => {
  const pack = sdk.newPack();
  registerDraftActions(pack, endpoint);
  assert.deepEqual(pack.formulas.map(f => f.name), ["CreateDraftEvent", "UpdateDraftLocation", "SaveDraftContent"]);
  for (const formula of pack.formulas) assert.equal(formula.isAction, true);
  const calls: any[] = [];
  const context: any = { fetcher: { fetch: async (request: any) => { calls.push(request); return { body: { result: { structuredContent: { id: "test-event", revision: 1 } } } }; } } };
  const create = pack.formulas[0];
  const args = ["retry-key", "Synthetic", "2026-11-12T15:00:00-08:00", "2026-11-12T16:00:00-08:00", "America/Los_Angeles", "Demo Room A", "Synthetic Go description"];
  await create.execute(args as never, context);
  await create.execute(args as never, context);
  const request = JSON.parse(calls[0].body);
  assert.equal(request.params.name, "create_event");
  assert.equal(request.params.arguments.idempotency_key, "retry-key");
  assert.equal(request.params.arguments.location, "Demo Room A");
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(calls[0].headers.Authorization, undefined);
  await pack.formulas[1].execute(["test-event", 1, "Demo Room B"] as never, context);
  assert.deepEqual(JSON.parse(calls[2].body).params, { name: "update_event", arguments: { event_id: "test-event", expected_revision: 1, location: "Demo Room B" } });
  await pack.formulas[2].execute(["test-event", 2, "flyer_brief", "Blue minimalist", ""] as never, context);
  assert.equal(JSON.parse(calls[3].body).params.arguments.kind, "flyer_brief");
  await assert.rejects(() => pack.formulas[2].execute(["test-event", 2, "send", "bad", ""] as never, context));
  assert.equal(calls.length, 4);
});
test("a failed MCP result never reports a saved event", async () => {
  const context: any = { fetcher: { fetch: async () => ({ body: { result: { isError: true } } }) } };
  await assert.rejects(() => callDraftTool(context, endpoint, "create_event", {}), /not confirmed saved/);
});
