import { writeFile } from "node:fs/promises";

const argument = process.argv[2];
if (!argument) {
  console.error("Usage: npm run configure -- https://YOUR-DOMAIN/mcp");
  process.exit(1);
}
const endpoint = new URL(argument);
if (endpoint.protocol !== "https:" || endpoint.username || endpoint.password ||
    endpoint.search || endpoint.hash || endpoint.pathname !== "/mcp" ||
    ["localhost", "127.0.0.1", "[::1]"].includes(endpoint.hostname) ||
    endpoint.hostname.endsWith(".example.com")) {
  throw new Error("Use your deployed public HTTPS /mcp URL with no credentials, query, or fragment.");
}
await writeFile(new URL("./config.ts", import.meta.url),
  `// Public endpoint only. Credentials are entered when installing the connector in Go.\nexport const mcpEndpoint = ${JSON.stringify(endpoint.href)};\n`);
console.log("Connector endpoint updated. Run npm run check before uploading.");
