"""Build deploy_to_vercel payload for chatbot + stock. No secrets."""

from __future__ import annotations

import base64
import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    wanted = [
        "app/page.tsx",
        "app/layout.tsx",
        "app/globals.css",
        "app/page.module.css",
        "app/api/query/route.ts",
        "app/api/modules/route.ts",
        "lib/stock.ts",
        "next.config.ts",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "vercel.json",
        "scripts/ensure-stock.mjs",
    ]
    files: list[dict[str, str]] = []
    for rel in wanted:
        path = root / rel
        if not path.is_file():
            raise SystemExit(f"missing {rel}")
        files.append(
            {
                "file": rel,
                "data": path.read_text(encoding="utf-8"),
                "encoding": "utf-8",
            }
        )
    ned = root / "next-env.d.ts"
    if ned.is_file():
        files.append(
            {
                "file": "next-env.d.ts",
                "data": ned.read_text(encoding="utf-8"),
                "encoding": "utf-8",
            }
        )
    else:
        files.append(
            {
                "file": "next-env.d.ts",
                "data": (
                    '/// <reference types="next" />\n'
                    '/// <reference types="next/image-types/global" />\n'
                ),
                "encoding": "utf-8",
            }
        )
    files.append({"file": "stock/.gitkeep", "data": "", "encoding": "utf-8"})
    stock_root = root / "stock"
    for path in stock_root.rglob("*"):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        try:
            files.append(
                {"file": rel, "data": raw.decode("utf-8"), "encoding": "utf-8"}
            )
        except UnicodeDecodeError:
            files.append(
                {
                    "file": rel,
                    "data": base64.b64encode(raw).decode("ascii"),
                    "encoding": "base64",
                }
            )
    payload = {
        "target": "production",
        "name": "wsai-factory-chatbot",
        "teamId": "team_L3hzaZoX58ujoz7nZSL6znAH",
        "files": files,
        "projectSettings": {"framework": "nextjs"},
    }
    out = root / "_mcp_deploy_payload.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "n_files": len(files),
                "has_page": any(item["file"] == "app/page.tsx" for item in files),
                "has_duration": any(
                    "duration-toolkit" in item["file"] for item in files
                ),
                "size": out.stat().st_size,
                "path": str(out),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
