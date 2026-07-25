import { NextResponse } from "next/server";

import { assertChatbotSecret } from "@/lib/auth";
import { queryStock, StockQueryError } from "@/lib/stock";

export const runtime = "nodejs";

type QueryBody = {
  query: string;
};

function isQueryBody(value: unknown): value is QueryBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return typeof record.query === "string";
}

export async function POST(request: Request): Promise<NextResponse> {
  const denied = assertChatbotSecret(request);
  if (denied !== null) {
    return denied;
  }
  let payload: unknown;
  try {
    payload = await request.json();
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "bad_json",
          message: `body must be JSON (${detail})`,
        },
      },
      { status: 400 },
    );
  }
  if (!isQueryBody(payload)) {
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "query_required_string",
          message: "body.query must be a string",
        },
      },
      { status: 400 },
    );
  }
  try {
    const result = await queryStock(payload.query);
    return NextResponse.json({ ok: true, result });
  } catch (error: unknown) {
    if (error instanceof StockQueryError) {
      return NextResponse.json(
        {
          ok: false,
          error: { code: error.code, message: error.message },
        },
        { status: 404 },
      );
    }
    throw error;
  }
}
