import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";

const maximumRequestBytes = 1_048_576;
const allowedMethods = new Set(["GET", "POST", "PATCH", "DELETE"]);

type RouteContext = { params: Promise<{ path: string[] }> };

function jsonError(status: number, detail: string, errorCode: string): Response {
  return Response.json(
    { detail, error_code: errorCode, extra: {} },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

async function readBoundedBody(request: Request): Promise<ArrayBuffer | Response | undefined> {
  if (request.method === "GET" || request.method === "DELETE" || !request.body) {
    return undefined;
  }
  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null) {
    const size = Number(declaredLength);
    if (!Number.isSafeInteger(size) || size < 0) {
      return jsonError(400, "Invalid request content length.", "INVALID_CONTENT_LENGTH");
    }
    if (size > maximumRequestBytes) {
      return jsonError(413, "Request body exceeds the configured size limit.", "REQUEST_TOO_LARGE");
    }
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maximumRequestBytes) {
      await reader.cancel();
      return jsonError(413, "Request body exceeds the configured size limit.", "REQUEST_TOO_LARGE");
    }
    chunks.push(value);
  }
  const body = new ArrayBuffer(total);
  const output = new Uint8Array(body);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

async function proxy(request: Request, context: RouteContext): Promise<Response> {
  if (!allowedMethods.has(request.method)) {
    return jsonError(405, "Method not allowed.", "METHOD_NOT_ALLOWED");
  }

  const baseUrl = process.env.FAULTLINE_API_BASE_URL?.replace(/\/+$/, "");
  const tokenPath = process.env.FAULTLINE_API_TOKEN_FILE;
  if (!baseUrl || !tokenPath) {
    return jsonError(503, "The server-side API proxy is not configured.", "API_PROXY_NOT_CONFIGURED");
  }

  let token: string;
  try {
    token = (await readFile(tokenPath, "utf8")).trim();
  } catch {
    return jsonError(503, "The server-side API proxy is not configured.", "API_PROXY_NOT_CONFIGURED");
  }
  if (token.length < 32 || /[^A-Za-z0-9._~-]/.test(token)) {
    return jsonError(503, "The server-side API proxy is not configured.", "API_PROXY_NOT_CONFIGURED");
  }

  const body = await readBoundedBody(request);
  if (body instanceof Response) return body;

  try {
    const { path } = await context.params;
    const target = new URL(
      `${path.map((part) => encodeURIComponent(part)).join("/")}${new URL(request.url).search}`,
      `${baseUrl}/`,
    );
    const headers = new Headers({
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      "X-Request-ID": randomUUID(),
    });
    const contentType = request.headers.get("content-type");
    if (body && contentType) headers.set("Content-Type", contentType);

    const upstream = await fetch(target, {
      method: request.method,
      headers,
      ...(body === undefined ? {} : { body }),
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    });
    const responseHeaders = new Headers();
    for (const header of [
      "cache-control",
      "content-type",
      "retry-after",
      "x-content-type-options",
      "x-request-id",
    ]) {
      const value = upstream.headers.get(header);
      if (value) responseHeaders.set(header, value);
    }
    return new Response(upstream.status === 204 ? null : upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return jsonError(502, "Faultline API is unavailable.", "API_PROXY_UNAVAILABLE");
  }
}

export const runtime = "nodejs";
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
