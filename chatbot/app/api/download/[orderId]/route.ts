import { NextRequest, NextResponse } from "next/server";

import { downloadTokenMatches } from "@/lib/download-token";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ orderId: string }>;
};

export async function GET(
  request: NextRequest,
  context: RouteContext,
): Promise<NextResponse> {
  const { orderId } = await context.params;
  if (typeof orderId !== "string" || orderId.trim() === "") {
    return NextResponse.json(
      { ok: false, code: "bad_order_id", message: "orderId required" },
      { status: 400 },
    );
  }
  const token = request.nextUrl.searchParams.get("token");
  if (typeof token !== "string" || token.trim() === "") {
    return NextResponse.json(
      { ok: false, code: "missing_token", message: "query token required" },
      { status: 401 },
    );
  }
  const key = process.env.WSAI_FACTORY_WEBHOOK_KEY;
  if (typeof key !== "string" || key.trim() === "") {
    return NextResponse.json(
      {
        ok: false,
        code: "missing_env",
        message: "WSAI_FACTORY_WEBHOOK_KEY missing",
      },
      { status: 500 },
    );
  }
  if (!downloadTokenMatches(orderId.trim(), token.trim(), key.trim())) {
    return NextResponse.json(
      { ok: false, code: "bad_token", message: "download token mismatch" },
      { status: 401 },
    );
  }
  const base = process.env.FACTORY_BACKEND_URL;
  if (typeof base !== "string" || base.trim() === "") {
    return NextResponse.json(
      {
        ok: false,
        code: "missing_env",
        message: "FACTORY_BACKEND_URL missing",
      },
      { status: 500 },
    );
  }
  const url = `${base.replace(/\/$/, "")}/order/${encodeURIComponent(orderId.trim())}/zip`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${key.trim()}`,
      Accept: "application/zip",
    },
  });
  if (!response.ok) {
    const text = await response.text();
    return NextResponse.json(
      {
        ok: false,
        code: "backend_zip_failed",
        message: `backend zip HTTP ${response.status}: ${text.slice(0, 400)}`,
      },
      { status: 502 },
    );
  }
  const bytes = await response.arrayBuffer();
  return new NextResponse(bytes, {
    status: 200,
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="${orderId.trim()}.zip"`,
    },
  });
}
