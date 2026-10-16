import { readFile } from "node:fs/promises";

const config = await readFile(new URL("./config.ts", import.meta.url), "utf8");
if (config.includes("hackathon.example.com")) {
  console.error("Set your deployed HTTPS endpoint with npm run configure before creating or uploading the connector.");
  process.exit(1);
}
