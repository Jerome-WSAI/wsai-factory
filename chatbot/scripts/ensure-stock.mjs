import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const chatbotRoot = path.resolve(here, "..");
const dest = path.join(chatbotRoot, "stock");
const sourceCandidates = [
  path.resolve(chatbotRoot, "..", "pipeline", "stock"),
  dest,
];

function countModuleFiles(root) {
  let count = 0;
  function walk(dir) {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      const st = statSync(full);
      if (st.isDirectory()) {
        walk(full);
        continue;
      }
      if (name === ".gitkeep" || name === "index.json") {
        continue;
      }
      count += 1;
    }
  }
  walk(root);
  return count;
}

let source = null;
for (const candidate of sourceCandidates) {
  if (!existsSync(candidate)) {
    continue;
  }
  if (countModuleFiles(candidate) === 0) {
    continue;
  }
  source = candidate;
  break;
}

if (source === null) {
  console.error(
    JSON.stringify({
      ok: false,
      error: "stock_empty_or_missing",
      tried: sourceCandidates,
    }),
  );
  process.exit(1);
}

if (path.resolve(source) !== path.resolve(dest)) {
  if (existsSync(dest)) {
    rmSync(dest, { recursive: true, force: true });
  }
  mkdirSync(path.dirname(dest), { recursive: true });
  cpSync(source, dest, { recursive: true });
}

console.log(
  JSON.stringify({
    ok: true,
    source,
    destination: dest,
    file_count: countModuleFiles(dest),
  }),
);
