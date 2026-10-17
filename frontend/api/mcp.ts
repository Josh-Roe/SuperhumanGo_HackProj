import { forwardMcp } from "../server/proxy.ts";

// Keeps the public connector at the website /mcp while Python owns the protocol/tools.
const forward = forwardMcp;
export const GET = forward;
export const POST = forward;
export const DELETE = forward;
export const OPTIONS = forward;
