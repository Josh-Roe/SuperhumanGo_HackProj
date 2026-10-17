// Temporary testing setup until the backend has a permanent host: expose the local backend
// through a Cloudflare quick tunnel and point the Go connector at the tunnel's random hostname.
// Usage: npm run tunnel [-- --port 8000] [-- --no-upload]
import { spawn, spawnSync } from "node:child_process";

const args = process.argv.slice(2);
const portIndex = args.indexOf("--port");
const port = portIndex >= 0 ? args[portIndex + 1] : "8000";
const upload = !args.includes("--no-upload");

const local = await fetch(`http://127.0.0.1:${port}/api/health`).catch(() => null);
if (!local?.ok) {
  console.error(`No backend answering on 127.0.0.1:${port}. Start it first: npm run dev:backend`);
  process.exit(1);
}

const tunnel = spawn("cloudflared", ["tunnel", "--no-autoupdate", "--url", `http://127.0.0.1:${port}`], {
  stdio: ["ignore", "ignore", "pipe"],
});
tunnel.on("error", () => {
  console.error("cloudflared not found. Install it: brew install cloudflared");
  process.exit(1);
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => tunnel.kill(signal));
tunnel.on("exit", (code) => {
  console.log("Tunnel closed; the connector URL is now dead until you run this again.");
  process.exit(code ?? 0);
});

const origin = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("cloudflared printed no tunnel URL in 30s")), 30_000);
  tunnel.stderr.on("data", (chunk) => {
    const match = chunk.toString().match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/);
    if (match) {
      clearTimeout(timer);
      resolve(match[0]);
    }
  });
});

// A new quick-tunnel hostname takes a few seconds to resolve.
let reachable = false;
for (let attempt = 0; attempt < 30 && !reachable; attempt++) {
  const response = await fetch(`${origin}/api/health`).catch(() => null);
  reachable = Boolean(response?.ok);
  if (!reachable) await new Promise((done) => setTimeout(done, 2000));
}
if (!reachable) {
  console.error(`${origin} never became reachable.`);
  tunnel.kill();
  process.exit(1);
}

const run = (command, commandArgs) =>
  spawnSync(command, commandArgs, { stdio: "inherit", cwd: import.meta.dirname }).status === 0;

if (!run("node", ["configure.mjs", `${origin}/mcp`]) || !run("npm", ["run", "check"])) {
  tunnel.kill();
  process.exit(1);
}
if (upload) {
  const notes = `Temporary tunnel ${origin}`;
  const ok = run("npx", ["packs", "upload", "pack.ts", "--notes", notes]) &&
    run("npx", ["packs", "release", "pack.ts", "--notes", notes]);
  if (!ok) console.error("Connector upload/release failed; Go still points at the previous URL.");
}

console.log(`
Backend tunnel: ${origin}
  Go connector:  ${origin}/mcp${upload ? " (uploaded and released)" : " (config.ts only; not uploaded)"}
  Dashboard:     npm run dev:frontend, then open http://127.0.0.1:5173
  Vercel site:   set BACKEND_ORIGIN=${origin}/ in Vercel and redeploy (changes every run)

Do not commit config.ts with this hostname. Ctrl-C closes the tunnel.`);
