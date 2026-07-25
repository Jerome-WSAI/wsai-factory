"""Stock chatbot library: query pipeline/stock files on disk. Never invents code."""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TypedDict, cast

from pipeline_lib import PipelineError


class StockFileHit(TypedDict):
    job_id: str
    module: str
    relative_path: str
    content: str


class StockQueryResult(TypedDict):
    query: str
    stock_root: str
    hit_count: int
    hits: list[StockFileHit]
    note: str


def assert_under_stock(path: Path, stock_root: Path) -> None:
    resolved = path.resolve()
    root = stock_root.resolve()
    if root not in resolved.parents and resolved != root:
        raise PipelineError(
            "path_escape",
            f"refusing path outside stock: {resolved}",
            "chatbot",
        )


def list_stock_files(stock_root: Path) -> list[Path]:
    if not stock_root.is_dir():
        raise PipelineError(
            "stock_missing",
            f"stock root missing: {stock_root}",
            "chatbot",
        )
    files: list[Path] = []
    for path in stock_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name == ".gitkeep":
            continue
        if path.name == "index.json":
            continue
        assert_under_stock(path, stock_root)
        files.append(path)
    return sorted(files)


def parse_stock_file(path: Path, stock_root: Path) -> StockFileHit:
    assert_under_stock(path, stock_root)
    rel = path.relative_to(stock_root)
    parts = rel.parts
    if len(parts) < 2:
        raise PipelineError(
            "bad_stock_layout",
            f"expected stock/<job_id>/<module>/... got {rel.as_posix()}",
            "chatbot",
        )
    job_id = parts[0]
    module = parts[1]
    relative_path = Path(*parts[1:]).as_posix()
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PipelineError(
            "stock_not_utf8",
            f"stock file not utf-8: {path}",
            "chatbot",
        ) from exc
    return {
        "job_id": job_id,
        "module": module,
        "relative_path": relative_path,
        "content": content,
    }


def query_stock(query: str, stock_root: Path) -> StockQueryResult:
    if query.strip() == "":
        raise PipelineError(
            "empty_query",
            "query must be non-empty",
            "chatbot",
        )
    needle = query.strip().lower()
    hits: list[StockFileHit] = []
    for path in list_stock_files(stock_root):
        hit = parse_stock_file(path, stock_root)
        blob = f"{hit['job_id']} {hit['module']} {hit['relative_path']} {hit['content']}".lower()
        if needle in blob:
            hits.append(hit)
    if len(hits) == 0:
        raise PipelineError(
            "no_stock_match",
            f"no stock file matches query={query!r} under {stock_root}",
            "chatbot",
        )
    return {
        "query": query,
        "stock_root": "stock",
        "hit_count": len(hits),
        "hits": hits,
        "note": "content is read verbatim from pipeline/stock; no code is generated",
    }


def html_page() -> str:
    return """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <title>WSAI Factory Stock Chatbot</title>
  <style>
    body { font-family: Georgia, serif; margin: 2rem; max-width: 48rem; }
    textarea { width: 100%; min-height: 4rem; }
    pre { white-space: pre-wrap; background: #f4f4f0; padding: 1rem; }
  </style>
</head>
<body>
  <h1>WSAI Factory Stock Chatbot</h1>
  <p>Recherche dans <code>pipeline/stock</code> uniquement. Aucun code inventé.</p>
  <form id="f">
    <label for="q">Requête</label>
    <textarea id="q" name="q" required></textarea>
    <button type="submit">Chercher dans le stock</button>
  </form>
  <pre id="out"></pre>
  <script>
    document.getElementById("f").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const q = document.getElementById("q").value;
      const res = await fetch("/api/query", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query: q})
      });
      const text = await res.text();
      document.getElementById("out").textContent = text;
    });
  </script>
</body>
</html>
"""


def make_handler(stock_root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _write(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                page = html_page().encode("utf-8")
                self._write(200, page, "text/html; charset=utf-8")
                return
            self._write(404, b'{"error":"not_found"}', "application/json")

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/api/query":
                self._write(404, b'{"error":"not_found"}', "application/json")
                return
            length_raw = self.headers.get("Content-Length")
            if length_raw is None:
                self._write(400, b'{"error":"missing_content_length"}', "application/json")
                return
            length = int(length_raw)
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                msg = json.dumps(
                    {"error": "bad_json", "detail": str(exc)},
                    ensure_ascii=False,
                ).encode("utf-8")
                self._write(400, msg, "application/json; charset=utf-8")
                return
            if not isinstance(payload, dict):
                self._write(400, b'{"error":"payload_not_object"}', "application/json")
                return
            data = cast(dict[str, object], payload)
            query_obj = data.get("query")
            if not isinstance(query_obj, str):
                self._write(400, b'{"error":"query_required_string"}', "application/json")
                return
            try:
                result = query_stock(query_obj, stock_root)
            except PipelineError as exc:
                msg = json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "at_stage": exc.at_stage,
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self._write(404, msg, "application/json; charset=utf-8")
                return
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2)
            self._write(200, body.encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, fmt: str, *args: object) -> None:
            return

    return Handler


def serve(stock_root: Path, host: str, port: int) -> None:
    handler = make_handler(stock_root)
    server = ThreadingHTTPServer((host, port), handler)
    print(
        json.dumps(
            {
                "ok": True,
                "serving": True,
                "url": f"http://{host}:{port}/",
                "stock_root": str(stock_root.resolve()).replace("\\", "/"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    server.serve_forever()
