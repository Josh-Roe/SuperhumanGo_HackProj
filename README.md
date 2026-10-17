# SuperhumanGo Hackathon Project

React + TypeScript frontend, Python API and MCP tools, and an optional CPU model-serving path for [MTC x Grammarly: Agents in Action](https://mtc-x-grammarly.devpost.com/).

The approved product is an event organizer website: create event details, prepare Canva material and inclusion checks, distribute invitations through Gmail/Google Calendar, and propagate changes. **Superhuman Go powers the writing and coordination, with its built-in Grammarly assistance.** The website name and final primary track remain undecided. Current code is a scaffold; the product plan and assigned tasks are documented, not implemented by the planning update.

## Run locally

Install Node.js 24, Python 3.11+, and [uv](https://docs.astral.sh/uv/getting-started/installation/). From the repository root:

```sh
npm run setup
uv sync --project backend --extra dev
cp backend/.env.example backend/.env
```

Start two terminals:

```sh
npm run dev:backend
```

```sh
npm run dev:frontend
```

Open **http://localhost:5173**. Vite proxies `/api` to port 8000. API documentation is at **http://127.0.0.1:8000/docs**. MCP stays unavailable until `MCP_AUTH_TOKEN` is set in `backend/.env`; the browser needs no token.

## Validate

```sh
npm run check
```

This runs frontend lint, tests, and production build; backend lint and tests; and TypeScript/SDK connector validation. Lockfiles are committed for both npm projects and the Python backend. GitHub Actions repeats these checks and builds the Docker images.

## Project layout

| Directory | Responsibility |
| --- | --- |
| `frontend/` | React TSX UI, typed API client, Vite proxy |
| `backend/` | FastAPI REST API, authenticated MCP tools, optional Python ONNX CPU runtime |
| `integrations/superhuman/` | Official Packs SDK connector for Go |
| `inference/` | Optional C++ ONNX Runtime runner |
| `models/` | Local model artifacts, excluded from Git |
| `deploy/`, `compose.yaml` | VPS containers and Caddy HTTPS routing |
| `docs/` | Integration, deployment, team workflow, presentation handoffs |

## Superhuman Go

Go calls our hosted `/mcp` tools through an authenticated connector built with `@codahq/packs-sdk`. Follow [Superhuman setup](docs/SUPERHUMAN.md) to configure the endpoint, register/upload the connector, and test it in your account. The starter tools prove the connection; product-specific tools will follow the project decision.

Live activation needs a public HTTPS endpoint and an eligible Superhuman account. No provider credentials, remote connector, or live AI session are included in this scaffold.

## Team and deployment

- [Shared product context](PROJECT_CONTEXT.md) — read with all four member contexts before work; update only your own member context.
- [Four assignments and copy-ready agent prompts](docs/TEAM_TASKS.md)
- [Initial integration contract](docs/INTEGRATION_CONTRACT.md)
- [Four-member workflow and VS Code Live Share](docs/TEAM_WORKFLOW.md)
- [Team roster](TEAM.md) and [contribution guide](CONTRIBUTING.md)
- [Architecture and API handoff](docs/ARCHITECTURE.md)
- [VPS deployment and CPU models](docs/DEPLOYMENT.md)
- [Presentation and Canva handoff](docs/PRESENTATION.md)
- [Hackathon brief and submission checklist](docs/HACKATHON.md)

Teammate access awaits the supplied GitHub usernames. VPS configuration is prepared; no server has been provisioned or deployed.
