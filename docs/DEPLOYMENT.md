# VPS and CPU deployment

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
