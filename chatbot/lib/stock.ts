import { promises as fs } from "node:fs";
import path from "node:path";

export type StockFileHit = {
  job_id: string;
  module: string;
  relative_path: string;
  content: string;
};

export type StockQueryResult = {
  query: string;
  stock_root: string;
  hit_count: number;
  hits: StockFileHit[];
  note: string;
};

export type StockModuleSummary = {
  job_id: string;
  module: string;
  files: string[];
};

export class StockQueryError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "StockQueryError";
    this.code = code;
  }
}

function resolveStockRoot(): string {
  return path.join(process.cwd(), "stock");
}

async function walkFiles(root: string): Promise<string[]> {
  const out: string[] = [];
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
      out.push(full);
    }
  }
  await walk(root);
  return out.sort();
}

function assertUnderStock(filePath: string, stockRoot: string): void {
  const resolved = path.resolve(filePath);
  const root = path.resolve(stockRoot);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    throw new StockQueryError(
      "path_escape",
      `refusing path outside stock: ${resolved}`,
    );
  }
}

async function parseStockFile(
  filePath: string,
  stockRoot: string,
): Promise<StockFileHit | null> {
  assertUnderStock(filePath, stockRoot);
  const rel = path.relative(stockRoot, filePath);
  const parts = rel.split(path.sep).filter((part) => part.length > 0);
  if (parts.length < 2) {
    throw new StockQueryError(
      "bad_stock_layout",
      `expected stock/<job_id>/<module>/... got ${rel.replace(/\\/g, "/")}`,
    );
  }
  const jobId = parts[0];
  const moduleName = parts[1];
  if (jobId === undefined || moduleName === undefined) {
    throw new StockQueryError(
      "bad_stock_layout",
      `expected stock/<job_id>/<module>/... got ${rel.replace(/\\/g, "/")}`,
    );
  }
  const relativePath = parts.slice(1).join("/");
  const buf = await fs.readFile(filePath);
  if (buf.includes(0)) {
    // Binary stock assets are skipped for text query.
    return null;
  }
  const content = buf.toString("utf8").replace(/^\uFEFF/, "");
  return {
    job_id: jobId,
    module: moduleName,
    relative_path: relativePath,
    content,
  };
}

export async function listModules(): Promise<StockModuleSummary[]> {
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
    throw new StockQueryError("stock_empty", `no modules under ${stockRoot}`);
  }
  return modules;
}

export async function queryStock(query: string): Promise<StockQueryResult> {
  const trimmed = query.trim();
  if (trimmed === "") {
    throw new StockQueryError("empty_query", "query must be non-empty");
  }
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
  const needle = trimmed.toLowerCase();
  const files = await walkFiles(stockRoot);
  const hits: StockFileHit[] = [];
  for (const filePath of files) {
    const hit = await parseStockFile(filePath, stockRoot);
    if (hit === null) {
      continue;
    }
    const blob =
      `${hit.job_id} ${hit.module} ${hit.relative_path} ${hit.content}`.toLowerCase();
    if (blob.includes(needle)) {
      hits.push(hit);
    }
  }
  if (hits.length === 0) {
    throw new StockQueryError(
      "no_stock_match",
      `no stock file matches query=${query}`,
    );
  }
  return {
    query,
    stock_root: "stock",
    hit_count: hits.length,
    hits,
    note: "content is read verbatim from chatbot/stock (synced from pipeline/stock); no code is generated",
  };
}
