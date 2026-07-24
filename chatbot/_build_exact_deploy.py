import base64
import json
from pathlib import Path

root = Path(".")
rels = [
    "package.json",
    "next.config.ts",
    "vercel.json",
    "tsconfig.json",
    "scripts/ensure-stock.mjs",
    "lib/stock.ts",
    "app/api/query/route.ts",
    "app/api/modules/route.ts",
    "app/layout.tsx",
    "app/page.tsx",
    "app/globals.css",
]
files: list[dict[str, str]] = []
for rel in rels:
    files.append({"file": rel, "data": (root / rel).read_text(encoding="utf-8")})
files.append(
    {
        "file": "next-env.d.ts",
        "data": '/// <reference types="next" />\n/// <reference types="next/image-types/global" />\n',
    }
)
files.append({"file": "stock/.gitkeep", "data": ""})
for path in sorted((root / "stock").rglob("*")):
    if not path.is_file():
        continue
    if path.name == ".gitkeep":
        continue
    rel = path.relative_to(root).as_posix()
    if path.suffix == ".py":
        files.append(
            {
                "file": rel,
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                "encoding": "base64",
            }
        )
    else:
        files.append({"file": rel, "data": path.read_text(encoding="utf-8")})

payload = {
    "target": "production",
    "name": "wsai-factory-chatbot",
    "teamId": "team_L3hzaZoX58ujoz7nZSL6znAH",
    "projectSettings": {"framework": "nextjs"},
    "files": files,
}
Path("_exact_deploy.json").write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps({"count": len(files), "names": [f["file"] for f in files]}))
