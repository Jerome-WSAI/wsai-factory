import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

import { StockQueryError } from "@/lib/stock";

export const runtime = "nodejs";

type StockModuleSummary = {
  job_id: string;
  module: string;
  files: string[];
};

function resolveStockRoot(): string {
  return path.join(process.cwd(), "stock");
}

async function listModules(): Promise<StockModuleSummary[]> {
  const stockRoot = resolveStockRoot();
  try {
    await fs.access(stockRoot);
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new StockQueryError(
      "stock_missing",
      `stock root missing: ${stockRoot} (${detail})`,
    );
  }
  const byKey = new Map<string, StockModuleSummary>();
  async function walk(dir: string): Promise<void> {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(full);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      if (entry.name === ".gitkeep" || entry.name === "index.json") {
        continue;
      }
      const rel = path.relative(stockRoot, full);
      const parts = rel.split(path.sep).filter((part) => part.length > 0);
      if (parts.length < 2) {
        continue;
      }
      const jobId = parts[0];
      const moduleName = parts[1];
      if (jobId === undefined || moduleName === undefined) {
        continue;
      }
      const key = `${jobId}/${moduleName}`;
      const existing = byKey.get(key);
      const fileRel = parts.slice(1).join("/");
      if (existing === undefined) {
        byKey.set(key, {
          job_id: jobId,
          module: moduleName,
          files: [fileRel],
        });
      } else {
        existing.files.push(fileRel);
      }
    }
  }
  await walk(stockRoot);
  const modules = [...byKey.values()].sort((a, b) => {
    const left = `${a.job_id}/${a.module}`;
    const right = `${b.job_id}/${b.module}`;
    return left.localeCompare(right);
  });
  if (modules.length === 0) {
    throw new StockQueryError(
      "stock_empty",
      `no modules under ${stockRoot}`,
    );
  }
  return modules;
}

export async function GET(): Promise<NextResponse> {
  try {
    const modules = await listModules();
    return NextResponse.json({
      ok: true,
      result: {
        stock_root: path.resolve(resolveStockRoot()).replace(/\\/g, "/"),
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
