# Superhuman Go integration

## Supported connection

The official [MCP connector guide](https://coda.io/packs/build/latest/guides/blocks/mcp/) supports hosted Streamable HTTP MCP tools with bearer-token or OAuth authentication. This project uses that route:

```text
Superhuman Go → Packs SDK connector → HTTPS /mcp → Python tools
Browser React UI → /api → Python REST API
```

This is a tool integration into Go. It does not assume an undocumented API for sending chatbot prompts from the backend to Go. The browser’s status cards report server configuration, not proof that Go has installed or called the connector.

## Local development

Copy `backend/.env.example` to `backend/.env`. Generate a token locally and put it in `MCP_AUTH_TOKEN`:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
npm run dev:backend
```

The MCP server rejects requests without a valid bearer token. `MCP_AUTH_TOKEN` is a deployment check token: it reaches only `workspace_status` and `count_text`. Event tools require a **per-organizer connector token**, which resolves to that organizer's events only.

### Event tools (Member 3)

| Tool | Effect |
| --- | --- |
| `get_event` | Current revision, facts, and saved Go content; no invitee emails |
| `list_go_work` / `claim_go_work` | Queue of prose to write and replies to classify |
| `save_generated_content` | Stores Go-written prose for one revision (`producer: superhuman_go`, `needs_review`) |
| `preview_distribution` | Calendar create/update and Gmail draft/replace/change-notice plan, with blockers |
| `execute_distribution` | Runs an organizer-made approval; idempotent Calendar upsert + Gmail send |
| `sync_rsvps` / `get_reply` / `record_rsvp_classification` / `list_rsvps` | Calendar statuses plus Go-classified replies |

The backend is the only writer to Calendar and Gmail. Go agent instructions: [`integrations/superhuman/agent/INSTRUCTIONS.md`](../integrations/superhuman/agent/INSTRUCTIONS.md).

### Dev mode (before Supabase)

```sh
WORKFLOW_DEV_MODE=1 DEV_CONNECTOR_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" \
DEV_INVITEES=you+test@example.com npm run dev:backend
```

This seeds the in-memory event `dev-event-1`. `DEV_CONNECTOR_TOKEN` is both the Go connector token and the bearer for `/api/dev/*`: `POST .../events/dev-event-1/prepare`, `GET .../events/dev-event-1`, `POST .../approve {content_id, action}`, `POST .../revise {location, starts_at, ends_at}`, `POST /api/dev/google/connect`. State is lost on restart and is not Supabase evidence.

Google: create an OAuth client (Web application) with redirect `https://YOUR-DOMAIN/api/dev/google/callback`. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI`. Scopes: `calendar.events`, `gmail.compose`, `gmail.readonly`, `openid`, `email`. In testing mode, add test users. Use only invitees who agreed to receive test mail.

The [official tutorial](https://coda.io/packs/build/latest/tutorials/build/mcp/) requires a hosted endpoint. A localhost server and SDK validation alone cannot verify live Go behavior.

## Connect to your account

1. Deploy the server using [the VPS guide](DEPLOYMENT.md), with a public HTTPS hostname and a strong `MCP_AUTH_TOKEN`.
2. Configure and validate the connector:

   ```sh
   cd integrations/superhuman
   npm ci
   npm run configure -- https://YOUR-DOMAIN/mcp
   npm run check
   ```

3. Authenticate and create the connector using the official Pack CLI:

   ```sh
   npm run register
   npm run create
   npm run upload
   npx packs release pack.ts --notes "Initial hackathon connector"
   ```

   Registration requires your account token. The generated `.coda.json` contains credentials and is ignored by Git. `.coda-pack.json` tracks the remote Pack identity and is also ignored; share access through the account rather than committing credentials. `config.ts` contains only the public endpoint and can be committed.

4. In Superhuman Go, open **Connectors**, find the connector, install it, and enter the same bearer token used by the server. The official tutorial lists Pro or higher for Go and Doc Maker access to create the Pack; use the hackathon’s provisioned access if supplied.
5. Start a chat and ask Go to use `workspace_status`. Then install with the organizer connector token (dev: `DEV_CONNECTOR_TOKEN`), queue work with `POST /api/dev/events/dev-event-1/prepare`, and say "Process my event work." Confirm in the connector session logs that `list_go_work`, `get_event` and `save_generated_content` were called, and that `GET /api/dev/events/dev-event-1` shows content with `producer: superhuman_go`.

Until step 5 succeeds, record the state as **locally tested; live Go connection unverified**. Backend `verified` remains false deliberately: the server cannot infer remote installation from configuration.

## Configure a Go agent

After installing the connector, use Go’s [agent builder](https://support.grammarly.com/hc/en-us/articles/47453002811021-Create-and-configure-agents-with-the-agent-builder) to configure the event-writing/coordination agent and its authorized tools. Verify actual triggers and account grants before claiming fully automatic website-to-Go execution. A manual Go invocation processing queued event work is the labeled MVP fallback. The four development roles in [the task plan](TEAM_TASKS.md) are separate from this product agent.

Add product tools through the backend’s MCP service and test their inputs and outputs. Give read-only tools the `readOnlyHint` annotation; tools with side effects should retain Go’s confirmation behavior. Keep API credentials in backend environment settings and never in `VITE_*` variables or browser code.

Do not upload or release the example endpoint in `config.ts`. The configure command requires a real HTTPS `/mcp` URL; the committed example exists only so the SDK can be validated before a domain is available.
