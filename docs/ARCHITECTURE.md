# Architecture

The approved product is an event organizer website. React collects details, design/inclusion review and distribution choices; Superhuman Go generates prose and coordinates event tools; Python executes reliable provider operations; Supabase supplies Auth, Postgres and artifact Storage. Read [the global brief](../PROJECT_CONTEXT.md), [four member contexts](TEAM_TASKS.md), and [event contract](INTEGRATION_CONTRACT.md). The code is still the reusable scaffold; event features below are the implementation plan.

## Components

| Component | Technology | Responsibility |
| --- | --- | --- |
| Web interface | React, TypeScript/TSX, Vite | User interface and REST client |
| Application backend | Python, FastAPI | `/api/health`, `/api/status`, future product APIs and server-side integrations |
| Planned event data | Supabase Auth, Postgres, Storage | Organizer identity/ownership, versioned event state, private RSVP, stored documents/flyer exports |
| Planned event providers | Gmail, Google Calendar, Canva | Go-coordinated invitations, Calendar IDs/RSVP, current flyer versions and change propagation |
| Agent tool server | Python FastMCP, streamable HTTP at `/mcp` | Expose backend tools to an authenticated connector |
| Superhuman Go connector | Superhuman Go Packs SDK | Connect Go to the project's MCP tools; see [setup](SUPERHUMAN.md) |
| Optional inference | ONNX Runtime CPU in Python, separate C++ runner | Load an externally supplied ONNX model after its input/output contract is agreed |
| Optional hosting | CPU VPS, containers, reverse proxy | Host the web app and backend when needed; see [deployment](DEPLOYMENT.md) |

During development, Vite serves the frontend on port `5173` and proxies `/api` requests to the backend on `8000`. The browser does not receive provider credentials or the MCP bearer token. The Go connector reaches the backend's public HTTPS `/mcp` endpoint when externally configured.

REST serves the web interface; MCP exposes tools to the Go connector. They share application logic where needed, while keeping their transport and authentication requirements explicit. No external Go installation is implied by a healthy local API.

## Integration contract

FastAPI's generated `/openapi.json` and `/docs` describe the implemented REST contract. Coordinate request/response changes with the frontend owner before merging. The scaffold status endpoint reports configuration and readiness; product outcomes must have their own endpoints once the team decides the use case.

Initial responses:

```jsonc
// GET /api/health
{"status": "ok", "service": "backend"}

// GET /api/status, before credentials or a model are configured
{
  "superhuman": {
    "transport": "mcp",
    "configured": false,
    "verified": false,
    "endpoint": "/mcp"
  },
  "model": {"configured": false, "runtime": "not_configured"}
}
```

The MCP scaffold exposes `workspace_status` and `count_text`. A configured bearer token changes configuration readiness, while `verified: false` explicitly avoids claiming that Go has installed or called the connector. When a local model file and the required Python dependencies are present, status can identify `onnxruntime-cpu`; it does not establish model quality or measured performance.

Keep integration configuration in environment variables documented in the relevant `.env.example`. Use local environment files for real secrets. Frontend `VITE_*` values are public build configuration and must never contain credentials.

## ML and CPU inference

The Python backend is the first integration point for ML libraries and APIs. No training pipeline or trained model is assumed. When a custom model is chosen, document its provenance, license, preprocessing, tensor names/shapes/dtypes, outputs, and a known input/output example. Store large artifacts outside Git and record how to obtain them.

Export to ONNX only when the chosen model supports it. Validate output parity before measuring CPU latency. Compare Python and C++ under the same model, preprocessing, threads, warmup, and inputs; include end-to-end request latency. Select the C++ path only if the measurements justify its extra integration work. The optional runner is not automatically an HTTP model service.

## Open decisions

Website name, final primary track, provider accounts/credentials, Go activation/automatic trigger availability, eligible Canva template, exact schemas, and VPS/domain remain open. The chosen event workflow and Supabase data direction supersede earlier idea exploration. Follow the four member contexts for progress. Custom model training/ONNX optimization is deferred until the core event/Go loop works.
