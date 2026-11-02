import type { NextRequest } from "next/server";
import { sameOrigin } from "@/lib/origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const route = path.join("/");
  if (!(
    (route === "status" && request.method === "GET") ||
    (route === "research" && request.method === "POST")
  ))
    return Response.json({ detail: "Unknown route" }, { status: 404 });
  if (request.method === "POST") {
    const origin = request.headers.get("origin");
    if (
      !sameOrigin(
        origin,
        request.headers.get("host"),
        request.nextUrl.protocol,
        process.env.VERIWEB_PUBLIC_ORIGIN,
      )
    )
      return Response.json({ detail: "Origin not allowed" }, { status: 403 });
  }
  const base =
    process.env.VERIWEB_API_URL ??
    `http://${process.env.VERIWEB_API_HOST ?? "127.0.0.1"}:${process.env.VERIWEB_API_PORT ?? "8000"}`;
  try {
    const text = request.method === "POST" ? await request.text() : undefined;
    if (text && text.length > 4096)
      return Response.json(
        { detail: "Question is too large" },
        { status: 413 },
      );
    const signal = AbortSignal.any([
      request.signal,
      AbortSignal.timeout(route === "status" ? 6000 : 610000),
    ]);
    const response = await fetch(new URL(`/api/${route}`, base), {
      method: request.method,
      body: text,
      headers: { "Content-Type": "application/json" },
      signal,
      cache: "no-store",
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "Research service is unavailable. Start the Python backend and retry.",
      },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
