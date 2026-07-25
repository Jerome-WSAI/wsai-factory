"""Live prod path: catalog → chat → zip → open smoke. No secret prints."""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "pipeline"
BASE = "https://wsai-factory-backend.onrender.com"


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "WSAI_FACTORY_WEBHOOK_KEY":
            return value.strip().strip('"').strip("'")
    raise RuntimeError("WSAI_FACTORY_WEBHOOK_KEY missing in .env")


def request(method: str, path: str, body: dict[str, object] | None, key: str) -> tuple[int, bytes, str]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")


def main() -> None:
    key = load_key()
    status, raw, _ = request("GET", "/catalog", None, key)
    catalog = json.loads(raw.decode("utf-8"))
    modules = catalog.get("modules")
    if status != 200 or not isinstance(modules, list) or len(modules) == 0:
        raise SystemExit(f"catalog failed status={status} body={raw[:400]!r}")
    print(f"catalog_ok count={len(modules)}")
    first = modules[0]
    job_id = first["job_id"]
    module = first["module"]
    message = (
        f"Je veux un outil pret base sur {job_id}/{module}. "
        "Assemble maintenant sans autre question."
    )
    status, raw, _ = request("POST", "/chat", {"message": message, "history": []}, key)
    chat = json.loads(raw.decode("utf-8"))
    (PROOF / "proof_prod_chat.json").write_text(
        json.dumps(chat, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    order = chat.get("order")
    print(f"chat_status={status} ok={chat.get('ok')} order={order}")
    if not isinstance(order, dict) or order.get("queued") is not True:
        raise SystemExit(f"order not queued: {chat.get('decision')}")
    order_id = order["order_id"]
    status, raw, ctype = request("GET", f"/order/{order_id}/zip", None, key)
    zip_path = PROOF / "proof_prod_download.zip"
    zip_path.write_bytes(raw)
    print(f"zip_status={status} bytes={len(raw)} ctype={ctype}")
    if status != 200 or len(raw) < 22:
        raise SystemExit("zip download failed")
    out = PROOF / "proof_prod_open"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(out)
    index = out / "index.html"
    html = index.read_text(encoding="utf-8")
    if "{{TOOL_NAME}}" in html:
        raise SystemExit("placeholder left in index.html")
    files = [p for p in out.rglob("*") if p.is_file()]
    print(f"open_ok index_bytes={len(html)} files={len(files)}")
    summary = {
        "ok": True,
        "base": BASE,
        "order_id": order_id,
        "zip_bytes": len(raw),
        "index_bytes": len(html),
        "files": len(files),
        "job_id": job_id,
        "module": module,
    }
    (PROOF / "proof_prod_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
