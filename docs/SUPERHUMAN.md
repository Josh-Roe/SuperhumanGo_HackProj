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

### Guided pipeline tools (Member 3)

One Go conversation walks the organizer through every step; approval happens in chat (decision 2026-10-16).

| Tool | Effect |
| --- | --- |
| `event_progress` | Stage list (details, writing, review, inclusion, flyer, send, rsvps) with `next_stage`; read-only |
| `approve_draft` | Marks the invitation/change notice the organizer approved in chat `ready`; edited text is saved as `producer: organizer` |
| `save_inclusion_facts` | Organizer's yes/no/unknown answers, merged with saved facts; unknown stays unsourced |
| `send_invitations` | Records the exact-content approval and runs the same idempotent distribution; retries never resend |

The backend is the only writer to Calendar and Gmail. Go agent instructions: [`integrations/superhuman/agent/INSTRUCTIONS.md`](../integrations/superhuman/agent/INSTRUCTIONS.md).

### Dev mode (before Supabase)

```sh
WORKFLOW_DEV_MODE=1 DEV_CONNECTOR_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" \
DEV_INVITEES=you+test@example.com npm run dev:backend
```

This seeds the in-memory event `dev-event-1`. `DEV_CONNECTOR_TOKEN` is both the Go connector token and the bearer for `/api/dev/*`: `POST .../events/dev-event-1/prepare`, `GET .../events/dev-event-1`, `POST .../approve {content_id, action}`, `POST .../revise {location, starts_at, ends_at}`, `POST /api/dev/google/connect`. State is lost on restart and is not Supabase evidence.

Google: create an OAuth client (Web application) with redirect `https://YOUR-DOMAIN/api/dev/google/callback`. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI`. Scopes: `calendar.events`, `gmail.compose`, `gmail.readonly`, `openid`, `email`. In testing mode, add test users. Use only invitees who agreed to receive test mail.

### Temporary tunnel (testing only, until the backend has a permanent host)

With the backend running on port 8000, `cd integrations/superhuman && npm run tunnel` opens a Cloudflare quick tunnel, writes its `/mcp` URL into `config.ts`, and uploads and releases the connector (`-- --no-upload` skips that). The hostname changes on every run and dies with the process or a sleeping laptop. Test the dashboard locally with `npm run dev:frontend`; the Vercel site needs `BACKEND_ORIGIN` set to the printed origin and a redeploy. Do not commit `config.ts` with a tunnel hostname.

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

## Deploy

Go needs a stable public HTTPS `/mcp`. Quick tunnels (`*.trycloudflare.com`) change hostname on restart, so the connector breaks. These steps assume Member 2's deployment artifacts (see handoff below) exist. Until they do, use the [VPS guide](DEPLOYMENT.md).

1. **Backend host.** Render: New → Blueprint → this repo (or Web Service → Docker, context `backend`, Dockerfile `backend/Dockerfile`). Any Docker host works. Health check path: `/api/health`. The free tier sleeps when idle, so wake it (`curl https://HOST/api/health`) before a demo.
2. **Env vars** (host dashboard, never in Git): `MCP_AUTH_TOKEN`, `APP_DOMAIN`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `CREDENTIAL_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. Optional: `ONNX_MODEL_PATH`. Dev mode only: `WORKFLOW_DEV_MODE=1`, `DEV_CONNECTOR_TOKEN`, `DEV_INVITEES`, `DEV_ORGANIZER_CONTACT`. Leave `WORKFLOW_DEV_MODE` unset in production.
3. **`APP_DOMAIN`** = the bare public hostname, e.g. `your-app.onrender.com`. Don't include a scheme, path or trailing slash. `/mcp` rejects other `Host` headers (DNS-rebinding protection), and CORS allows `https://APP_DOMAIN`.
4. **Google OAuth.** Set `GOOGLE_REDIRECT_URI=https://HOST/api/google/callback` (the production route), and add the same URI under the OAuth client's Authorized redirect URIs in Google Cloud Console. Dev mode uses `https://HOST/api/dev/google/callback` instead.
5. **Verify:** `curl -fsS https://HOST/api/health` returns `{"status":"ok",...}`, and `/api/status` reports `superhuman.configured: true`.
6. **Point the connector at the host and upload:**

   ```sh
   npm --prefix integrations/superhuman run configure -- https://HOST/mcp
   npm --prefix integrations/superhuman run check
   npm --prefix integrations/superhuman run upload
   ```

   Commit the updated `config.ts`, which holds only the public endpoint.
7. **Release from the Pack Studio web UI** (the Pack's page → Release). `npx packs release` refuses while the working tree has uncommitted changes.
8. **Re-sign in the Go connector** (Connectors → this Pack → sign in again), because the endpoint changed. Copy the token with no trailing newline. A trailing newline produced `<no HTTP response>` tool failures:

   ```sh
   printf %s "$TOKEN" | tr -d '\n' | pbcopy
   ```

   Then ask Go to run `workspace_status`.
9. **Vercel.** In the frontend project (Root Directory `frontend`), set the server-only `BACKEND_ORIGIN=https://HOST` (origin only, without `/api`) and the public `VITE_PUBLIC_MCP_URL=https://HOST/mcp`. Redeploy, because `VITE_*` values are baked in at build time. `frontend/vercel.json` already rewrites `/api/*` to `frontend/api/proxy.ts`, which forwards to `BACKEND_ORIGIN`. Check with `curl https://YOUR-VERCEL-APP/api/health`.

### Handoff to Member 2 (proposed)

Status: **proposed**, 2026-10-16. Member 2 owns these files. Member 3 has not edited them.

- **`backend/Dockerfile` CMD.** Bind to the host's `PORT`, trust the TLS proxy, and default `APP_DOMAIN` from Render:

  ```dockerfile
  ENV PORT=8000 FORWARDED_ALLOW_IPS="*"
  CMD ["sh", "-c", "export APP_DOMAIN=\"${APP_DOMAIN:-${RENDER_EXTERNAL_HOSTNAME:-}}\"; exec python -m uvicorn hackathon_backend.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers"]
  ```

  The current CMD hardcodes port 8000 and `--no-proxy-headers`. Render injects `PORT` (default 10000), so health checks fail there. Make `HEALTHCHECK` read `PORT` too. `PORT=8000` keeps Compose/Caddy unchanged. `FORWARDED_ALLOW_IPS="*"` is safe only when the container is reachable solely through the host proxy (Render edge or Caddy).
- **`backend/.dockerignore`.** Add `.env.*`, `!.env.example`, and `tests/`. The current file excludes only `.env`, although the Dockerfile copies only `pyproject.toml`, `uv.lock` and `src`.
- **`render.yaml`** (repo root). Use `type: web`, `runtime: docker`, `plan: free`, `dockerfilePath: ./backend/Dockerfile`, `dockerContext: ./backend`, and `healthCheckPath: /api/health`. Under `envVars`, list every name from step 2 with `sync: false`. `GOOGLE_REDIRECT_URI` is `https://HOST/api/google/callback`.
- **Vercel API base.** No change is needed. `BACKEND_ORIGIN` (server-only) is already read by `frontend/server/proxy.ts`. Add `BACKEND_ORIGIN` and `VITE_PUBLIC_MCP_URL` to the Vercel env-var docs/README deploy steps.
- **Evidence.** HEAD (`1752141`) exported to a temp dir: `uv run uvicorn hackathon_backend.main:app --port 8010` gave `/api/health` 200. Run locally, not containerized, because Docker isn't installed on this device. Nothing has been deployed or verified live.

## Configure a Go agent

After installing the connector, use Go’s [agent builder](https://support.grammarly.com/hc/en-us/articles/47453002811021-Create-and-configure-agents-with-the-agent-builder) to configure the event-writing/coordination agent and its authorized tools. Verify actual triggers and account grants before claiming fully automatic website-to-Go execution. A manual Go invocation processing queued event work is the labeled MVP fallback. The four development roles in [the task plan](TEAM_TASKS.md) are separate from this product agent.

Add product tools through the backend’s MCP service and test their inputs and outputs. Give read-only tools the `readOnlyHint` annotation; tools with side effects should retain Go’s confirmation behavior. Keep API credentials in backend environment settings and never in `VITE_*` variables or browser code.

Do not upload or release the example endpoint in `config.ts`. The configure command requires a real HTTPS `/mcp` URL; the committed example exists only so the SDK can be validated before a domain is available.
