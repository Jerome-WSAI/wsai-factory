import { NextResponse } from "next/server";

import { assertChatbotSecret } from "@/lib/auth";
import { listModules, StockQueryError } from "@/lib/stock";

export const runtime = "nodejs";

export async function GET(request: Request): Promise<NextResponse> {
  const denied = assertChatbotSecret(request);
  if (denied !== null) {
    return denied;
  }
  try {
    const modules = await listModules();
    return NextResponse.json({
      ok: true,
      result: {
        stock_root: "stock",
        module_count: modules.length,
        modules,
        note: "listing only; file contents served via POST /api/query from disk",
      },
    });
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
