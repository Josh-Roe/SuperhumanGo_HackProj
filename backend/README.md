# Python backend

Python 3.11+ FastAPI service with authenticated Streamable HTTP MCP tools. There is no application feature, trained model, or invented Superhuman API client in this scaffold.

From `backend/`:

```sh
cp .env.example .env
uv sync --extra dev
uv run --env-file .env python -m uvicorn hackathon_backend.main:app --reload --host 127.0.0.1 --port 8000
```

The service reads `MCP_AUTH_TOKEN`, `APP_DOMAIN`, and `ONNX_MODEL_PATH` from its process environment. It does **not** automatically load `.env`. The command above explicitly loads the backend `.env`; copy `backend/.env.example` before running it. From the repository root, `npm run dev:backend` uses the same backend `.env` file. Compose supplies these environment variables directly from root `.env`.

- `MCP_AUTH_TOKEN`: private bearer credential. Generate with `python -c 'import secrets; print(secrets.token_urlsafe(32))'`, store in `backend/.env` for local development (root `.env` for Compose), and configure it only in the external MCP client/server connection. Never put it in `VITE_*`, a browser bundle, commits, or screenshots.
- `APP_DOMAIN`: public hostname without scheme or path, e.g. `demo.example.com`. Defaults to local-only host/origin allowances if empty. `localhost` works for local use. Domain allowlisting keeps DNS rebinding protection enabled.
- `ONNX_MODEL_PATH`: optional existing ONNX file path inside the backend process/container. Requires the `ml` extra; unset by default. Compose model paths must refer to the container mount, e.g. `/models/model.onnx`.

## API contract

`GET /api/health` is public and returns:

```json
{"status":"ok","service":"backend"}
```

`GET /api/status` is public and defaults to:

```json
{
  "superhuman":{"transport":"mcp","configured":false,"verified":false,"endpoint":"/mcp"},
  "model":{"configured":false,"runtime":"not_configured"}
}
```

`superhuman.configured` means a local MCP bearer token exists. `verified` remains false because this service cannot confirm a connection in Superhuman Go. This is readiness information, not a live connectivity claim. `model.configured` means the configured file exists and the optional runtime packages are installed; it does not validate the model's contents or task quality. A configured model reports `runtime: "onnxruntime-cpu"`. No credential or model path is returned.

`POST /mcp` is the official Python MCP SDK's Streamable HTTP endpoint. All `/mcp` methods and subpaths require `Authorization: Bearer <MCP_AUTH_TOKEN>`; missing server configuration returns 503, missing/incorrect credentials return 401. The official SDK also enforces the configured Host and Origin allowlist. Tools:

- `workspace_status`: same readiness information as `/api/status`.
- `count_text`: deterministic character/word counts for up to 10,000 characters. This is a protocol utility, not an AI feature.

The FastAPI docs are at `/docs`. Frontend requests should use the same-origin `/api` proxy. Do not send the MCP bearer token to the frontend.

## Checks

```sh
uv sync --extra dev
uv run --extra dev python -m pytest -q
uv run --extra dev python -m ruff check .
uv run --extra dev python -m ruff format --check .
```

The test suite exercises MCP initialization, discovery and tool calls through its actual ASGI transport, missing/invalid authentication, host/origin rejection, environment handling, and response confidentiality. The optional inference test skips when the ML packages are absent.

```sh
uv sync --extra dev --extra ml
uv run --extra dev --extra ml python -m pytest -q
```

That adds real CPU inference against a tiny Identity graph generated in a temporary test directory. The graph is a test fixture, not a trained model. `OnnxRunner.run()` accepts exact input names and NumPy-compatible values, requests `CPUExecutionProvider`, and returns named outputs. Task-specific preprocessing, dtype/shape handling, output validation, training, and a product inference endpoint remain future work.

## Container

Build from this directory: `docker build -t superhuman-backend .`. Use `--build-arg INSTALL_ML=true` to include CPU ONNX Runtime. The locked dependencies are installed in `/opt/venv`; the service runs as an unprivileged user on port 8000. The default command disables forwarded proxy headers; same-origin routing does not require them.

## Outbound API integration boundary

`hackathon_backend.http_client.JSONAPIClient` is an async provider-neutral JSON client. Supply an explicit HTTPS base URL, optional server-side bearer token, and timeout when you add a real integration. HTTP is accepted only for localhost development. No upstream endpoint or provider credential is preconfigured. Requests accept paths relative to that base URL, never an alternate host; redirects are rejected. Use it with `async with` to close connections. `APIRequestError` strips upstream bodies, request URLs, and credentials from error messages.

```python
from hackathon_backend.http_client import JSONAPIClient

# Load the chosen provider URL/token on the server after selecting an integration.
async with JSONAPIClient(provider_base_url, bearer_token=provider_token) as client:
    payload = await client.request("GET", "/chosen-provider-path")
```

Mock transport tests cover success, credentials, timeouts, upstream failure, invalid JSON, redirects, host override rejection, and configuration validation. The example is an extension point; it does not contact a live provider until application code supplies one.
