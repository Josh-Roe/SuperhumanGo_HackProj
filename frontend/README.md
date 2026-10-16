# Frontend workspace

React + TypeScript + Vite starter. The dashboard checks the Python backend; it does not run agents or claim a verified Superhuman connection.

Use Node.js 24 LTS (Node 26 is also supported).

```sh
npm ci
npm run dev
```

Open `http://localhost:5173`. Run the backend separately on port 8000. Vite forwards `/api` to `http://127.0.0.1:8000`; override `BACKEND_PROXY_TARGET` in `.env.local` for a remote or forwarded backend. This is a server-side development setting, never an API key. Never put secrets in `VITE_*` variables: these are public in the browser bundle.

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

Tests cover backend readiness, credential-versus-verification messaging, failure and retry, and malformed responses. Production outputs `dist/`. The Dockerfile serves the build on port 80 through nginx with SPA fallback. The root deployment proxy must route `/api` and `/mcp` to the backend before forwarding other requests here. `npm run preview` previews static assets only; it is not the development API proxy or a production server.

The UI uses `GET /api/health` and `GET /api/status` from the backend. Credentials configured means server settings are present, not that Superhuman has connected. Optional model configuration also does not certify inference correctness.
