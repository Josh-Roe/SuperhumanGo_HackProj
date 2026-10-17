import process from "node:process";

// Server-only. Never inject backend credentials: authentication belongs to the caller.
async function forwardBackend(
  request: Request,
  mcp: boolean,
): Promise<Response> {
  const fail = (status: number, error: string) =>
    Response.json(
      { error },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  let origin: URL;
  try {
    origin = new URL(process.env.BACKEND_ORIGIN ?? "");
    if (
      origin.protocol !== "https:" ||
      origin.username ||
      origin.password ||
      origin.pathname !== "/" ||
      origin.search ||
      origin.hash ||
      origin.origin === new URL(request.url).origin
    )
      throw new Error();
  } catch {
    return fail(
      503,
      "Set server-only BACKEND_ORIGIN to the hosted HTTPS backend origin.",
    );
  }
  const incoming = new URL(request.url);
  if (
    mcp
      ? !["/mcp", "/api/mcp"].includes(incoming.pathname)
      : !incoming.pathname.startsWith("/api/")
  )
    return fail(404, "Unknown API route.");
  // Explicit rewrite supports nested routes in this Vite app without Next.js routing.
  const routedPath = incoming.searchParams.get("__backend_path");
  incoming.searchParams.delete("__backend_path");
  const path = mcp
    ? "/mcp"
    : routedPath === null
      ? incoming.pathname
      : `/api/${routedPath}`;
  const target = new URL(path + incoming.search, origin);
  if (
    target.origin !== origin.origin ||
    (!mcp && !target.pathname.startsWith("/api/"))
  )
    return fail(400, "Invalid API path.");
  const headers = new Headers({ Accept: "application/json" });
  for (const name of [
    "authorization",
    "content-type",
    "idempotency-key",
    ...(mcp
      ? ["accept", "mcp-protocol-version", "mcp-session-id", "last-event-id"]
      : []),
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const hasBody = !["GET", "HEAD"].includes(request.method);
    const body = hasBody ? await request.arrayBuffer() : undefined;
    if (body && body.byteLength > 1024 * 1024)
      return fail(413, "Request too large.");
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(20000)]),
    });
    // Redirects must not redirect organizer credentials or browser navigation to another host.
    if (upstream.status >= 300 && upstream.status < 400)
      return fail(
        502,
        "Backend redirected the API request. Check BACKEND_ORIGIN.",
      );
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const name of [
      "content-type",
      "www-authenticate",
      "retry-after",
      "mcp-session-id",
    ]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return fail(502, "The hosted event backend could not be reached.");
  }
}

export const forwardApi = (request: Request) => forwardBackend(request, false);
export const forwardMcp = (request: Request) => forwardBackend(request, true);
