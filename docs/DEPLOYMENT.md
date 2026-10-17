# Backend hosting and deployment

## Free native hosting: no VPS or Docker required

**Service created 2026-10-16; application activation pending.** Stable backend URL:
[superhuman-go-event-backend.onrender.com](https://superhuman-go-event-backend.onrender.com).
[Render dashboard](https://dashboard.render.com/web/srv-db9ccb7btjjs73b6pv50), workspace
`Grammarly Hackathon`, service `srv-db9ccb7btjjs73b6pv50`, Free/Oregon, auto-deploy off.
The first build used Render's default Python 3.14 because the service API has no
rootDir parameter; it failed before startup because the project requests Python 3.12
and managed downloads are disabled. Root `.python-version` fixed that: the next build
succeeded, and Render reports Python 3.12.15. Startup then correctly rejected missing
server credentials and unregistered persistent routes/MCP. An encryption key is now
set in Render, with a mode-0600 Git-ignored backup at `backend/.env.render`; do not
rotate it on the next deployment. The Supabase service-role key and Member 3
composition remain blockers. Do not mark the event API live until authenticated checks pass.

Keep Vercel for the frontend and the existing
Supabase project for Auth, data and files. Deploy the existing Python/FastAPI/MCP
process as a native web service. No database move or application rewrite is needed.

The root [render.yaml](../render.yaml) defines **Free** native Python hosting, the
Python 3.12 line, locked dependencies, and the platform `PORT`. It creates no extra
database and excludes optional ML. Auto-deploy is off until composition/account
gates pass. `RENDER_EXTERNAL_HOSTNAME` supplies the default `APP_DOMAIN`.

[Render Free](https://render.com/docs/free) sleeps after 15 idle minutes and normally
takes about one minute to wake. Hours, bandwidth and build quotas apply. An infinite
CPU calculation does not satisfy its inbound-traffic idle rule. Allow wake-up time
before a demo; this tier is not an always-on guarantee. [Koyeb Free](https://www.koyeb.com/docs/reference/instances)
is another small web-service option, with one-hour idle scale-to-zero. Check account
eligibility/card requirements and current limits at signup. Official limits checked
2026-10-16. Docker/Compose below remains an optional deployment path.

### Composition gate

Member 3 must include `api.create_router(settings, events=deps)` **before** the MCP
catch-all and pass the same `api.dependencies.create_tool_dependencies(settings)`
to `create_app(events=deps)`. The current `main.py` does not register those factories.
Event/task creation MCP tools and persistent organizer OAuth/Canva session flows
remain Member 3's integration. Development-store personal data/tokens are not Git data.

The native entrypoint `python -m hackathon_backend.api.serve` refuses startup if REST
routes are missing/hidden behind MCP, MCP uses a nonpersistent/different database,
server secrets are absent/invalid, or development mode is active. It prints blocker
names, never values. This is configuration validation, not proof of account grants.
Read-only local check with the intended server environment:

```sh
uv run --project backend --frozen --env-file backend/.env python -m hackathon_backend.api.readiness
```

### Render → Vercel → Go

1. Use the existing Render service above. To reproduce in another account, create a
   Blueprint from `render.yaml` and verify **Free**. Set existing `SUPABASE_URL`,
   `SUPABASE_PUBLISHABLE_KEY`, server-only `SUPABASE_SERVICE_ROLE_KEY` and
   `CREDENTIAL_ENCRYPTION_KEY` in Render. This chat's connector is management access,
   not a backend service key. Preserve the encryption key across deployments; rotation
   requires re-encrypting saved grants. Keep `WORKFLOW_DEV_MODE=0`.
2. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` when
   Member 3 supplies the persistent organizer OAuth callback/grant flow. The dev
   callback is not production multiuser authorization. Canva tokens/grants also stay
   server-side and organizer-scoped. Do not log credentials or private replies.
3. Deploy and verify HTTPS `/api/health`, `/api/config` and `/openapi.json`. Check
   event/task routes and authenticated two-account isolation; scaffold health alone
   is insufficient. Use the existing service above rather than creating a duplicate.
4. Vercel root directory: `frontend`. Set server-only
   `BACKEND_ORIGIN=https://BACKEND-HOST` and public build variable
   `VITE_PUBLIC_MCP_URL=https://BACKEND-HOST/mcp`; redeploy. Verify frontend `/api/config`
   forwards the backend response. Never inject a service/deployment key into browser calls.
5. Issue a personal Go connector token through authenticated `POST /api/connectors`.
   Install/update Go's connector to stable `/mcp`; authorize the same organizer.
   A Pack endpoint change requires reauthorization per Member 3's live handoff.
   Confirm `tools/list` includes create/update tools, then create a no-guests synthetic
   event through Go and compare its saved ID/revision in the website.
6. Verify actual private Storage upload/sign/read and restart persistence. Rehearse
   review/publish/update with explicitly authorized test recipients. Required assets
   must pass before Calendar invitations; uncertain provider writes require read-back
   reconciliation rather than blind reexecution.

To migrate from another host, retain Supabase/migrations, securely transfer environment
values and the same encryption key, change Vercel/MCP/OAuth URLs, and validate ownership
and operation receipts before stopping the old executor. Use one active provider writer
during cutover. Migration does not reset data or resend invitations.

## Container stack

`compose.yaml` runs the Python API and static React build behind Caddy. Only Caddy publishes ports. `/api/*` and `/mcp` go to Python; other routes go to the frontend. This keeps browser and API on the same origin.

For local containers, install Docker Engine/Desktop with Compose v2, then:

```sh
cp .env.example .env
```

Set a generated `MCP_AUTH_TOKEN` in `.env`, then:

```sh
docker compose config --quiet
docker compose up -d --build
curl --fail http://localhost/api/health
```

Open http://localhost. The root `.env` is for Compose; `backend/.env` is for the local Python server. Both are ignored by Git. Compose refuses to start without a token.

## Public VPS

Use a Linux VPS with Docker Engine and Compose v2. Choose CPU/RAM based on the actual model once one exists; no provider or paid resources have been selected.

1. Point the domain’s DNS at the VPS and allow inbound TCP 80/443; UDP 443 is optional for HTTP/3. Keep SSH available for administration.
2. Clone the repository, copy `.env.example` to `.env`, and set:

   ```dotenv
   APP_DOMAIN=your-public-hostname
   SITE_ADDRESS=your-public-hostname
   MCP_AUTH_TOKEN=your-generated-token
   INSTALL_ML=false
   ONNX_MODEL_PATH=
   ```

3. Run `docker compose config --quiet` and `docker compose up -d --build`. Caddy obtains HTTPS certificates when DNS resolves and the certificate challenge can reach the server. Certificate data persists in named volumes.
4. Verify `https://YOUR-DOMAIN/api/health`, inspect `docker compose ps` and `docker compose logs --tail=100`, then install and test the Go connector using [Superhuman setup](SUPERHUMAN.md).

For updates, commit local work first, pull `main` with `git pull --ff-only`, and rerun `docker compose up -d --build`. Stop services with `docker compose down`; certificate volumes are retained.

## Optional models

Python ML dependencies are optional:

```sh
uv sync --project backend --extra dev --extra ml
```

For containers, place the exported model in `models/`, set `INSTALL_ML=true`, set `ONNX_MODEL_PATH=/models/your-model.onnx`, and rebuild. The model directory mounts read-only. Model configuration and successful inference are separate checks; no trained model ships with this repository.

The [C++ runner](../inference/README.md) uses ONNX Runtime. Before promoting a Python model to C++, document preprocessing and shapes, verify output parity on fixed examples, and compare end-to-end latency on the same VPS. C++ and ONNX do not establish a performance win without measurements. No training job starts automatically.

## Verification boundaries

Local source checks verify UI behavior, REST endpoints, authenticated MCP protocol, and connector schema. Docker images, DNS, TLS, live Go installation, and model performance need their own runtime checks. Record the results actually observed; a passing SDK validation does not prove a reachable server.
during cutover. Migration does not reset data or resend invitations.
