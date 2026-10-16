export interface ProjectStatus {
  superhuman: {
    transport: "mcp";
    configured: boolean;
    verified: false;
    endpoint: "/mcp";
  };
  model: {
    configured: boolean;
    runtime: "onnxruntime-cpu" | "not_configured";
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new Error(`Backend returned HTTP ${response.status}.`);
  return response.json();
}

export async function loadProjectStatus(
  signal: AbortSignal,
): Promise<ProjectStatus> {
  const [health, status] = await Promise.all([
    getJson("/api/health", signal),
    getJson("/api/status", signal),
  ]);
  if (
    !isRecord(health) ||
    health.status !== "ok" ||
    health.service !== "backend"
  ) {
    throw new Error("Backend health response did not match the API contract.");
  }
  if (
    !isRecord(status) ||
    !isRecord(status.superhuman) ||
    !isRecord(status.model)
  ) {
    throw new Error("Backend status response did not match the API contract.");
  }
  const { superhuman, model } = status;
  if (
    superhuman.transport !== "mcp" ||
    typeof superhuman.configured !== "boolean" ||
    superhuman.verified !== false ||
    superhuman.endpoint !== "/mcp" ||
    typeof model.configured !== "boolean" ||
    !["onnxruntime-cpu", "not_configured"].includes(String(model.runtime))
  ) {
    throw new Error("Backend status response did not match the API contract.");
  }
  return status as unknown as ProjectStatus;
}
