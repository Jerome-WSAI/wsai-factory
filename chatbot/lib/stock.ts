import { promises as fs } from "node:fs";
import path from "node:path";

export type StockFileHit = {
  job_id: string;
  module: string;
  relative_path: string;
  absolute_path: string;
  content: string;
};

export type StockQueryResult = {
  query: string;
  stock_root: string;
  hit_count: number;
  hits: StockFileHit[];
  note: string;
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
): Promise<StockFileHit> {
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
  const content = buf.toString("utf8").replace(/^\uFEFF/, "");
  return {
    job_id: jobId,
    module: moduleName,
    relative_path: relativePath,
    absolute_path: path.resolve(filePath).replace(/\\/g, "/"),
    content,
  };
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
    stock_root: path.resolve(stockRoot).replace(/\\/g, "/"),
    hit_count: hits.length,
    hits,
    note: "content is read verbatim from chatbot/stock (synced from pipeline/stock); no code is generated",
  };
}
