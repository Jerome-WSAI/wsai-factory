import { createHmac, timingSafeEqual } from "crypto";

export function mintDownloadToken(orderId: string, secret: string): string {
  return createHmac("sha256", secret).update(`zip:${orderId}`).digest("hex");
}

export function downloadTokenMatches(
  orderId: string,
  token: string,
  secret: string,
): boolean {
  const expected = mintDownloadToken(orderId, secret);
  const left = Buffer.from(token, "utf8");
  const right = Buffer.from(expected, "utf8");
  if (left.length !== right.length) {
    return false;
  }
  return timingSafeEqual(left, right);
}
