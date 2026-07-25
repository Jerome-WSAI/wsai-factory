import { timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";

const SECRET_HEADER = "x-chatbot-secret";

function secretsEqual(provided: string, expected: string): boolean {
  const left = Buffer.from(provided, "utf8");
  const right = Buffer.from(expected, "utf8");
  if (left.length !== right.length) {
    return false;
  }
  return timingSafeEqual(left, right);
}

export function assertChatbotSecret(request: Request): NextResponse | null {
  const expected = process.env.CHATBOT_API_SECRET;
  if (typeof expected !== "string" || expected.trim() === "") {
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "secret_not_configured",
          message: "CHATBOT_API_SECRET is not configured",
        },
      },
      { status: 401 },
    );
  }
  const provided = request.headers.get(SECRET_HEADER);
  if (typeof provided !== "string" || !secretsEqual(provided, expected)) {
    return NextResponse.json(
      {
        ok: false,
        error: {
          code: "unauthorized",
          message: "missing or invalid x-chatbot-secret",
        },
      },
      { status: 401 },
    );
  }
  return null;
}
