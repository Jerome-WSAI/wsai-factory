/** Call WSAI Factory backend (Render) — assemble + zip, not GitHub Automations. */

export type OrderDemand = {
  order_id: string;
  tool_name: string;
  brief: string;
  modules: Array<{ job_id: string; module: string }>;
  created_at: string;
  status: "queued" | "assembled";
  download_path: string;
  zip_name: string;
};

export class OrderError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "OrderError";
    this.code = code;
  }
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new OrderError(
      "missing_env",
      `required env ${name} is missing or empty`,
    );
  }
  return value.trim();
}

function backendBase(): string {
  return requireEnv("FACTORY_BACKEND_URL").replace(/\/$/, "");
}

function backendKey(): string {
  return requireEnv("WSAI_FACTORY_WEBHOOK_KEY");
}

export type ChatBackendResult = {
  decision: Record<string, unknown>;
  order:
    | {
        queued: true;
        order_id: string;
        download_path: string;
        zip_name: string;
        module_count: number;
      }
    | { queued: false };
  catalog_size: number;
};

export async function chatViaBackend(params: {
  message: string;
  history: Array<{ role: string; content: string }>;
}): Promise<ChatBackendResult> {
  const response = await fetch(`${backendBase()}/chat`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${backendKey()}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      message: params.message,
      history: params.history,
    }),
  });
  const raw = await response.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new OrderError(
      "backend_bad_json",
      `backend non-JSON HTTP ${response.status}: ${detail}`,
    );
  }
  if (typeof parsed !== "object" || parsed === null) {
    throw new OrderError("backend_bad_shape", "backend root must be object");
  }
  const root = parsed as Record<string, unknown>;
  if (!response.ok || root.ok !== true) {
    const code = typeof root.code === "string" ? root.code : "backend_http_error";
    const message =
      typeof root.message === "string"
        ? root.message
        : `backend HTTP ${response.status}: ${raw.slice(0, 400)}`;
    throw new OrderError(code, message);
  }
  const decision = root.decision;
  if (typeof decision !== "object" || decision === null) {
    throw new OrderError("backend_no_decision", "missing decision");
  }
  const orderRaw = root.order;
  if (typeof orderRaw !== "object" || orderRaw === null) {
    throw new OrderError("backend_no_order", "missing order");
  }
  const orderObj = orderRaw as Record<string, unknown>;
  const queued = orderObj.queued === true;
  if (!queued) {
    return {
      decision: decision as Record<string, unknown>,
      order: { queued: false },
      catalog_size:
        typeof root.catalog_size === "number" ? root.catalog_size : 0,
    };
  }
  const orderId = orderObj.order_id;
  const downloadPath = orderObj.download_path;
  const zipName = orderObj.zip_name;
  if (typeof orderId !== "string" || typeof downloadPath !== "string") {
    throw new OrderError("backend_bad_order", "assembled order missing fields");
  }
  return {
    decision: decision as Record<string, unknown>,
    order: {
      queued: true,
      order_id: orderId,
      download_path: downloadPath,
      zip_name: typeof zipName === "string" ? zipName : `${orderId}.zip`,
      module_count:
        typeof orderObj.module_count === "number" ? orderObj.module_count : 0,
    },
    catalog_size: typeof root.catalog_size === "number" ? root.catalog_size : 0,
  };
}

/** Same-origin download only — never expose FACTORY_BACKEND_URL to the browser. */
export function localZipDownloadUrl(orderId: string, token: string): string {
  const id = encodeURIComponent(orderId);
  const t = encodeURIComponent(token);
  return `/api/download/${id}?token=${t}`;
}
