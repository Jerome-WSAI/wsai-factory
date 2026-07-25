"use server";

import { mintDownloadToken } from "@/lib/download-token";
import {
  chatViaBackend,
  localZipDownloadUrl,
  OrderError,
} from "@/lib/orders";
import {
  listModules,
  StockModuleSummary,
  StockQueryError,
} from "@/lib/stock";

export type ActionOk<T> = { ok: true; result: T };
export type ActionErr = { ok: false; error: { code: string; message: string } };

export type ChatTurnResult = {
  reply: string;
  status: string;
  question: string;
  order:
    | {
        queued: true;
        order_id: string;
        download_path: string;
        download_url: string;
        zip_name: string;
        module_count: number;
      }
    | { queued: false };
};

export async function loadModulesAction(): Promise<
  ActionOk<{ modules: StockModuleSummary[]; note: string }> | ActionErr
> {
  try {
    const modules = await listModules();
    return {
      ok: true,
      result: {
        modules,
        note: "catalogue stock (miroir) — assemblage via factory_backend Render",
      },
    };
  } catch (error: unknown) {
    if (error instanceof StockQueryError) {
      return {
        ok: false,
        error: { code: error.code, message: error.message },
      };
    }
    throw error;
  }
}

export async function chatTurnAction(params: {
  message: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
}): Promise<ActionOk<ChatTurnResult> | ActionErr> {
  try {
    const data = await chatViaBackend({
      message: params.message,
      history: params.history,
    });
    const decision = data.decision;
    const status =
      typeof decision.status === "string" ? decision.status : "unknown";
    const reply =
      typeof decision.reply === "string" ? decision.reply : "";
    const question =
      typeof decision.question === "string" ? decision.question : "";
    if (!data.order.queued) {
      return {
        ok: true,
        result: {
          reply,
          status,
          question,
          order: { queued: false },
        },
      };
    }
    const webhookKey = process.env.WSAI_FACTORY_WEBHOOK_KEY;
    if (typeof webhookKey !== "string" || webhookKey.trim() === "") {
      return {
        ok: false,
        error: {
          code: "missing_env",
          message: "WSAI_FACTORY_WEBHOOK_KEY missing for download token",
        },
      };
    }
    const token = mintDownloadToken(data.order.order_id, webhookKey.trim());
    return {
      ok: true,
      result: {
        reply,
        status,
        question,
        order: {
          queued: true,
          order_id: data.order.order_id,
          download_path: data.order.download_path,
          download_url: localZipDownloadUrl(data.order.order_id, token),
          zip_name: data.order.zip_name,
          module_count: data.order.module_count,
        },
      },
    };
  } catch (error: unknown) {
    if (error instanceof OrderError || error instanceof StockQueryError) {
      return {
        ok: false,
        error: { code: error.code, message: error.message },
      };
    }
    throw error;
  }
}
