#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import importlib.util

_bridge_path = Path(__file__).resolve().parent / "memory_bridge.py"
_spec = importlib.util.spec_from_file_location("memory_bridge", _bridge_path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load memory bridge module: {_bridge_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n).decode("utf-8", errors="replace") if n else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._json(200, {"ok": True})
        if parsed.path.startswith("/doc/"):
            doc_id = parsed.path[len("/doc/"):]
            try:
                return self._json(200, _mod.get_doc(doc_id))
            except FileNotFoundError:
                return self._json(404, {"error": "not_found", "doc_id": doc_id})
            except Exception as e:
                return self._json(400, {"error": str(e)})
        return self._json(404, {"error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
        except Exception as e:
            return self._json(400, {"error": f"invalid_json: {e}"})

        if parsed.path == "/search":
            q = body.get("query", "")
            mode = body.get("mode", "keyword")
            scope = body.get("scope", "all")
            limit = int(body.get("limit", 8))
            fn = _mod.semantic_search if mode == "semantic" else _mod.keyword_search
            hits = fn(query=q, scope=scope, limit=limit)
            return self._json(200, {
                "query": q,
                "mode": mode,
                "scope": scope,
                "results": [h.__dict__ for h in hits],
            })

        if parsed.path == "/facts":
            return self._json(200, _mod.upsert_fact(body))

        if parsed.path == "/entity-queue":
            return self._json(200, _mod.queue_entity(body))

        return self._json(404, {"error": "not_found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8091)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Memory API listening on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
