import { useEffect, useState } from "react";
import { loadProjectStatus } from "./api";
import type { ProjectStatus } from "./api";
import "./App.css";

type Connection =
  | { state: "loading" }
  | { state: "ready"; status: ProjectStatus }
  | { state: "error"; message: string };

const roles = [
  {
    number: "01",
    name: "Backend agent",
    area: "Python · APIs · ML",
    description: "Build services, connect tools, and prepare model inference.",
  },
  {
    number: "02",
    name: "Frontend agent",
    area: "React · TypeScript · UX",
    description: "Turn the team’s product direction into a clear, usable app.",
  },
  {
    number: "03",
    name: "Story & docs agent",
    area: "Documentation · Canva · Pitch",
    description: "Keep decisions, demo assets, and the presentation in sync.",
  },
];

function App() {
  const [connection, setConnection] = useState<Connection>({
    state: "loading",
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    let active = true;
    loadProjectStatus(controller.signal)
      .then((status) => {
        if (active) setConnection({ state: "ready", status });
      })
      .catch((error: unknown) => {
        if (active)
          setConnection({
            state: "error",
            message: controller.signal.aborted
              ? "The backend took too long to respond."
              : error instanceof Error
                ? error.message
                : "The backend could not be reached.",
          });
      })
      .finally(() => window.clearTimeout(timeout));
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [attempt]);

  function refresh() {
    setConnection({ state: "loading" });
    setAttempt((previous) => previous + 1);
  }

  const status = connection.state === "ready" ? connection.status : undefined;

  return (
    <div className="workspace">
      <header className="topbar">
        <a className="wordmark" href="#main">
          <span className="brand-icon" aria-hidden="true">
            ↗
          </span>{" "}
          GO / WORKSPACE
        </a>
        <span className="project-label">
          TEAM PROJECT <span className="tiny-dot" />
        </span>
      </header>

      <main id="main">
        <section className="intro" aria-labelledby="page-title">
          <p className="eyebrow">SUPERHUMAN GO HACKATHON</p>
          <h1 id="page-title">
            A shared place
            <br />
            to build what’s next<span>.</span>
          </h1>
          <p className="intro-copy">
            Three workstreams. One connected project. Your foundation for
            building with Superhuman Go.
          </p>
          <div className="stack">
            <span>React + TypeScript</span>
            <span>Python API</span>
            <span>CPU-ready infrastructure</span>
          </div>
        </section>

        <section className="systems" aria-labelledby="systems-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">LIVE CONNECTION</p>
              <h2 id="systems-title">Project readiness</h2>
            </div>
            <button
              className="refresh"
              onClick={refresh}
              disabled={connection.state === "loading"}
            >
              ↻{" "}
              <span>
                {connection.state === "loading"
                  ? "Checking…"
                  : "Refresh status"}
              </span>
            </button>
          </div>
          <div
            className={`connection-message ${connection.state}`}
            role="status"
            aria-live="polite"
          >
            <span className="status-dot" aria-hidden="true" />
            {connection.state === "loading" && "Checking the Python backend…"}
            {connection.state === "ready" &&
              "Backend connected · Health check passed"}
            {connection.state === "error" && (
              <span>
                Backend unavailable. {connection.message} Start the backend,
                then refresh status.
              </span>
            )}
          </div>
          <div className="readiness-grid">
            <article className="readiness-card">
              <span className="card-kicker">01 / INTEGRATION</span>
              <h3>Superhuman Go</h3>
              <span
                className={`badge ${status?.superhuman.configured ? "configured" : ""}`}
              >
                {status
                  ? status.superhuman.configured
                    ? "Credentials configured"
                    : "Setup required"
                  : "Awaiting backend"}
              </span>
              <p>
                {status?.superhuman.configured
                  ? "Credentials are set on the server. A live Superhuman connection has not yet been verified."
                  : "Connect the project’s MCP tools to Superhuman Go. Connection setup and verification are still required."}
              </p>
              <div className="card-footer">
                <code>/mcp</code>
                <span>MCP transport</span>
              </div>
            </article>
            <article className="readiness-card">
              <span className="card-kicker">02 / OPTIONAL INFERENCE</span>
              <h3>Model runtime</h3>
              <span
                className={`badge ${status?.model.configured ? "configured" : ""}`}
              >
                {status
                  ? status.model.configured
                    ? "Model configured"
                    : "No model configured"
                  : "Awaiting backend"}
              </span>
              <p>
                {status?.model.configured
                  ? "An ONNX model path is configured for CPU inference. Test it with the model’s documented inputs before your demo."
                  : "Start with API integrations. Add an ONNX model and CPU inference when the product needs it."}
              </p>
              <div className="card-footer">
                <code>
                  {status?.model.configured ? status.model.runtime : "ONNX"}
                </code>
                <span>Optional VPS deployment</span>
              </div>
            </article>
          </div>
        </section>

        <section className="team" aria-labelledby="team-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">BUILD TOGETHER</p>
              <h2 id="team-title">Three focused workstreams</h2>
            </div>
            <span className="section-note">Ownership starts here</span>
          </div>
          <div className="role-grid">
            {roles.map((role) => (
              <article className="role-card" key={role.number}>
                <span className="role-number">{role.number}</span>
                <h3>{role.name}</h3>
                <p className="role-area">{role.area}</p>
                <p>{role.description}</p>
                <span className="assignment">Teammate assignment pending</span>
              </article>
            ))}
          </div>
        </section>
      </main>
      <footer>
        <span>SUPERHUMANGO_HACKPROJ</span>
        <span>Foundation ready. Product direction comes next.</span>
      </footer>
    </div>
  );
}

export default App;
