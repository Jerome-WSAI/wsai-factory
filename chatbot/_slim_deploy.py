import json
from pathlib import Path

d = json.loads(Path("_mcp_args.json").read_text(encoding="utf-8"))
keep = {
    "app/api/modules/route.ts",
    "app/api/query/route.ts",
    "app/globals.css",
    "app/layout.tsx",
    "app/page.tsx",
    "lib/stock.ts",
    "next.config.ts",
    "package.json",
    "scripts/ensure-stock.mjs",
    "tsconfig.json",
    "vercel.json",
    "next-env.d.ts",
    "stock/.gitkeep",
    "stock/20260724T221552Z-vl-cas1-c9a4cd31/index.json",
    "stock/20260724T221552Z-vl-cas1-c9a4cd31/src/app.py",
    "stock/20260724T223721Z-vl-min1-aee210ae/index.json",
    "stock/20260724T223721Z-vl-min1-aee210ae/src/app.py",
    "stock/20260724T224301Z-vl-loop-cas1-5ca8819e/index.json",
    "stock/20260724T224301Z-vl-loop-cas1-5ca8819e/src/app.py",
}
d["files"] = [f for f in d["files"] if f["file"] in keep]
for f in d["files"]:
    if f["file"] == "next-env.d.ts":
        f["data"] = (
            '/// <reference types="next" />\n'
            '/// <reference types="next/image-types/global" />\n'
        )
Path("_mcp_slim.json").write_text(json.dumps(d), encoding="utf-8")
print(len(d["files"]), len(json.dumps(d)))
