"use server";

import {
  listModules,
  queryStock,
  StockModuleSummary,
  StockQueryError,
  StockQueryResult,
} from "@/lib/stock";

export type ActionOk<T> = { ok: true; result: T };
export type ActionErr = { ok: false; error: { code: string; message: string } };

export async function loadModulesAction(): Promise<
  ActionOk<{ modules: StockModuleSummary[]; note: string }> | ActionErr
> {
  try {
    const modules = await listModules();
    return {
      ok: true,
      result: {
        modules,
        note: "listing only; file contents served from disk via stock search",
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

export async function queryStockAction(
  query: string,
): Promise<ActionOk<StockQueryResult> | ActionErr> {
  try {
    const result = await queryStock(query);
    return { ok: true, result };
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
