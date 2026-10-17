# Canva OAuth setup for the backend owner

The implementation is in `providers/canva/oauth.py` and `oauth_routes.py`, registered by the existing `workflows/asset_wiring.py` composition. Main.py is unchanged. Go remains the user interface/orchestrator and writing agent; the backend uses the authorized Canva account to execute its flyer tools.

**Integration gate:** main `25baa36` now contains a separate REST OAuth implementation. This candidate uses Canva MCP authorization metadata and must be reviewed/adapted by lane L3; do not merge both callback registrations. The portal app currently enables MCP only. Actual token interoperability with REST export polling is unverified (A20).

## Canva portal already configured

- Draft app: **Event Workspace**, ID `AAHOGIOFimI`.
- Client ID: `OC-AaFHb2zo0SoS` (public identifier).
- Canva MCP enabled; REST integration disabled.
- Registered callback: `https://superhuman-go-event-backend.onrender.com/api/canva/callback`.
- The client secret is saved locally in **Git-ignored** `backend/.env.canva` with permissions 0600. Obtain its value through a secure channel from the app owner. Do not copy it into an issue, PR, chat prompt or browser bundle. The app is still a draft and has not been submitted for public release.

## Render deployment

The currently accessible Render account cannot manage this service. Its owner must grant access or perform these steps:

1. Have lane L3 review/adopt this OAuth candidate before deployment; A11 is already claimed by that lane, so avoid installing two connection implementations.
2. In the existing **superhuman-go-event-backend** service, add server environment variables:

   ```dotenv
   CANVA_CLIENT_ID=OC-AaFHb2zo0SoS
   CANVA_CLIENT_SECRET=<obtain securely>
   CANVA_REDIRECT_URI=https://superhuman-go-event-backend.onrender.com/api/canva/callback
   APP_URL=https://mtcxhackathon1.vercel.app
   ```

3. Retain the existing `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` and `CREDENTIAL_ENCRYPTION_KEY`. If a required server setting is missing, supply it securely; do not regenerate an existing encryption key, because it protects saved provider grants.
4. Run **one backend worker/replica** for this implementation. Pending consent state and refresh serialization live in memory; restarts invalidate pending consent. Shared leases/state are required before scaling workers.
5. Redeploy. Confirm `/api/health` is 200 and `/api/canva/status` without a session returns 401 (not 404). No credentials should be returned.
6. Set the frontend's `BACKEND_ORIGIN` to this backend origin and `VITE_PUBLIC_MCP_URL=https://superhuman-go-event-backend.onrender.com/mcp`; redeploy the frontend Settings control too.

## First actual organizer connection

1. Sign into the event website using the organizer's Supabase account. Open Settings → **Canva account**.
2. Click **Connect Canva**. The shared provider UI navigates to the backend bootstrap and then to Canva. Start from the website, rather than copying the short-lived start URL to another browser. The `/start` route requires the configured dashboard/backend referrer and sets a browser-bound cookie before redirecting to Canva.
3. Authorize the desired Canva account. The callback exchanges the code server-side with S256 PKCE and client Basic authentication, saves the grant in the existing encrypted `canva` vault record for the initiating organizer, and returns a success page. Tokens never enter URL parameters or the frontend.
4. Return to Settings and refresh the connection status. The authenticated `POST /api/canva/verify` endpoint checks creation, review and export tools; the shared UI does not yet expose this capability verification action. OAuth success alone is not proof that every required tool is granted.
5. Have Go queue/save `flyer_brief`, `flyer_copy`, `event_document`, `plain_language_summary` and `flyer_alt_text`. Use the existing start/poll/preview flyer tools. Approve the exact visual preview before export.
6. Verify a real PNG upload, signed current link and authorized test attachment. Repeat with changed time/location and inspect the new revision and old immutable bytes. Do not label the mocked acceptance suite as a live run.

Access tokens refresh shortly before expiry, and rotated refresh tokens are saved. An expired/nonrefreshable or legacy manually inserted grant requires reconnecting. An uncertain token exchange is not automatically retried. Pending-export polling and separate flyer approval UI were added upstream (`ad38df3`, `c308e0e`); their live behavior and MCP-token compatibility with REST polling still need verification. Same-design update registration and other pending handoffs remain documented in [ASSET_WIRING_HANDOFF.md](ASSET_WIRING_HANDOFF.md).

Sources checked 2026-10-16: [Canva access/client setup](https://www.canva.dev/docs/apps/mcp/access/), [Developer Portal quickstart](https://www.canva.dev/docs/apps/quickstart/), [protected-resource metadata](https://mcp.canva.com/.well-known/oauth-protected-resource/mcp), [authorization-server metadata](https://mcp.canva.com/.well-known/oauth-authorization-server). The OAuth client's endpoints/resource are fixed to the verified Canva service; no caller-selected token endpoint is accepted.
