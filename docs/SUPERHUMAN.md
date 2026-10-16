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

The MCP server rejects requests without the configured bearer token. `workspace_status` returns service readiness; `count_text` is a deterministic utility for checking a tool round trip. Neither is AI writing or the chosen event workflow. Member 3 adds event/content/operation tools and organizer-scoped authorization per [the contract](INTEGRATION_CONTRACT.md); a single global development token cannot authorize access to every organizer's data.

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
5. Start a chat and ask Go to use `workspace_status`, then to use `count_text` on a short sample. Confirm the tool call and response in connector session logs.

Until step 5 succeeds, record the state as **locally tested; live Go connection unverified**. Backend `verified` remains false deliberately: the server cannot infer remote installation from configuration.

## Configure a Go agent

After installing the connector, use Go’s [agent builder](https://support.grammarly.com/hc/en-us/articles/47453002811021-Create-and-configure-agents-with-the-agent-builder) to configure the event-writing/coordination agent and its authorized tools. Verify actual triggers and account grants before claiming fully automatic website-to-Go execution. A manual Go invocation processing queued event work is the labeled MVP fallback. The four development roles in [the task plan](TEAM_TASKS.md) are separate from this product agent.

Add product tools through the backend’s MCP service and test their inputs and outputs. Give read-only tools the `readOnlyHint` annotation; tools with side effects should retain Go’s confirmation behavior. Keep API credentials in backend environment settings and never in `VITE_*` variables or browser code.

Do not upload or release the example endpoint in `config.ts`. The configure command requires a real HTTPS `/mcp` URL; the committed example exists only so the SDK can be validated before a domain is available.
