#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from config.pipeline_paths import get_paths

P = get_paths()
REPO_ROOT = Path(P.repo_root)
MEMORY_ROOT = Path(P.memory_root)
AUDIT_DIR = P.data_root / "logs"
AUDIT_FILE = AUDIT_DIR / "memory_upserts.jsonl"
FACTS_FILE = MEMORY_ROOT / "99_runtime" / "chat_facts.jsonl"


@dataclass
class SearchHit:
    doc_id: str
    filename: str
    score: float
    snippet: str
    edition_tag: str = "SR3"
    page: str | None = None


def _iter_docs(scope: str = "all") -> Iterable[Path]:
    if not MEMORY_ROOT.exists():
        return []
    roots: list[Path] = []
    s = (scope or "all").lower()
    if s in {"all", "campaign"}:
        roots.append(MEMORY_ROOT / "campaign")
    if s in {"all", "sr3", "sr3_rules", "rules", "lore"}:
        roots.append(MEMORY_ROOT / "lore")
        roots.append(MEMORY_ROOT / "topics")
        roots.append(MEMORY_ROOT / "00_sources" / "rules_references")
    roots.append(MEMORY_ROOT / "90_derived")

    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.md"):
            rp = str(p.resolve())
            if rp in seen:
                continue
            seen.add(rp)
            yield p


def _doc_id(p: Path) -> str:
    try:
        rel = p.resolve().relative_to(MEMORY_ROOT.resolve())
        return rel.as_posix()
    except Exception:
        return p.name


def _snippet(text: str, idx: int, span: int = 220) -> str:
    if idx < 0:
        return text[:span].replace("\n", " ").strip()
    start = max(0, idx - span // 3)
    end = min(len(text), idx + span)
    return text[start:end].replace("\n", " ").strip()


def keyword_search(query: str, scope: str = "all", limit: int = 8) -> list[SearchHit]:
    q = (query or "").strip()
    if not q:
        return []

    terms = [t for t in re.split(r"\s+", q.lower()) if t]
    hits: list[SearchHit] = []

    for doc in _iter_docs(scope):
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        low = text.lower()
        score = 0.0
        first_idx = -1
        for term in terms:
            c = low.count(term)
            if c:
                score += c
                if first_idx < 0:
                    first_idx = low.find(term)
        if score <= 0:
            continue
        hits.append(
            SearchHit(
                doc_id=_doc_id(doc),
                filename=doc.name,
                score=float(score),
                snippet=_snippet(text, first_idx),
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: max(1, min(limit, 30))]


def semantic_search(query: str, scope: str = "all", limit: int = 8) -> list[SearchHit]:
    # Fallback semantic mode: keyword retrieval until embedding index endpoint is wired.
    return keyword_search(query=query, scope=scope, limit=limit)


def get_doc(doc_id: str, max_chars: int = 8000) -> dict:
    p = (MEMORY_ROOT / doc_id).resolve()
    if not str(p).startswith(str(MEMORY_ROOT.resolve())):
        raise ValueError("doc_id outside memory root")
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(doc_id)
    text = p.read_text(encoding="utf-8", errors="replace")
    return {
        "doc_id": doc_id,
        "filename": p.name,
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def upsert_fact(payload: dict) -> dict:
    FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    now = int(time.time())
    row = {
        "ts": now,
        "fact": payload.get("fact", "").strip(),
        "entity": payload.get("entity", "").strip(),
        "source": payload.get("source", "discord"),
        "channel": payload.get("channel", ""),
        "confidence": payload.get("confidence", "medium"),
        "tags": payload.get("tags", []),
    }

    with FACTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    audit = {
        "ts": now,
        "action": "upsert_fact",
        "filename": FACTS_FILE.name,
        "entity": row["entity"],
        "source": row["source"],
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit, ensure_ascii=False) + "\n")

    return {"ok": True, "written": str(FACTS_FILE), "audit": str(AUDIT_FILE)}


def queue_entity(payload: dict) -> dict:
    queue_file = MEMORY_ROOT / "entity_request_queue.jsonl"
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    row = {
        "ts": now,
        "entity": payload.get("entity", "").strip(),
        "note": payload.get("note", "").strip(),
        "status": "incoming",
        "source": payload.get("source", "openclaw"),
    }
    with queue_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True, "written": str(queue_file)}


def _start_service(cmd: list[str], log_name: str) -> dict:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = AUDIT_DIR / log_name
    with log_path.open("a", encoding="utf-8") as logf:
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=logf, stderr=logf, start_new_session=True)
    return {"pid": proc.pid, "log": str(log_path), "cmd": " ".join(cmd)}


def restart(service: str = "all", wiki_port: int = 8889, api_port: int = 8091) -> dict:
    service = (service or "all").lower()
    actions = []

    if service in {"all", "wiki"}:
        pat = str(REPO_ROOT / "05_serving" / "knowledge_wiki_server.py")
        subprocess.run(["pkill", "-f", pat], capture_output=True)
        started = _start_service(
            ["python3", str(REPO_ROOT / "05_serving" / "knowledge_wiki_server.py"), "--port", str(wiki_port)],
            "knowledge_wiki_server.log",
        )
        actions.append({"service": "wiki", "status": "restarted", **started})

    if service in {"all", "api"}:
        pat = str(REPO_ROOT / "05_serving" / "memory_api_server.py")
        subprocess.run(["pkill", "-f", pat], capture_output=True)
        started = _start_service(
            ["python3", str(REPO_ROOT / "05_serving" / "memory_api_server.py"), "--port", str(api_port)],
            "memory_api_server.log",
        )
        actions.append({"service": "api", "status": "restarted", **started})

    return {"ok": True, "service": service, "actions": actions}


def rebuild(target: str = "", scope: str = "all") -> dict:
    scope = (scope or "all").lower()
    cmds: list[list[str]] = []

    kb_cmd = ["python3", str(REPO_ROOT / "03_organization" / "build_campaign_kb.py")]
    if target.strip():
        kb_cmd += ["--target", target.strip()]

    if scope in {"all", "campaign", "entity"}:
        cmds.append(kb_cmd)
    if scope in {"all", "campaign"}:
        cmds.append(["python3", str(REPO_ROOT / "03_organization" / "build_entity_manifest.py")])
        cmds.append(["python3", str(REPO_ROOT / "03_organization" / "build_campaign_intro_timeline.py")])

    ran = []
    for cmd in cmds:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        ran.append({
            "cmd": " ".join(cmd),
            "code": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        })
        if proc.returncode != 0:
            return {"ok": False, "target": target, "scope": scope, "runs": ran}

    return {"ok": True, "target": target, "scope": scope, "runs": ran}
