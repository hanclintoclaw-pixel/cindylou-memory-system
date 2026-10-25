#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from config.pipeline_paths import get_paths

P = get_paths()
REPO_ROOT = Path(P.repo_root)
CODE_ROOT = Path(P.code_root)
MEMORY_ROOT = Path(P.memory_root)
AUDIT_DIR = P.data_root / "logs"
AUDIT_FILE = AUDIT_DIR / "memory_upserts.jsonl"
FACTS_FILE = MEMORY_ROOT / "99_runtime" / "chat_facts.jsonl"
WORKSPACE_ROOT = Path(
    os.environ.get(
        "CINDY_WORKSPACE_ROOT",
        str(Path.home() / ".openclaw" / "workspace-cindylou"),
    )
)
CAMPAIGN_WIKI_ROOT = Path(
    os.environ.get(
        "CAMPAIGN_WIKI_ROOT",
        str(CODE_ROOT / "campaign-wiki"),
    )
)
SCAN_MOUNTED_CAMPAIGN = (
    os.environ.get("MEMORY_SCAN_MOUNTED_CAMPAIGN", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
DATE_NOTE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\.md$")

# Returned doc_ids are resolvable by get_doc: relative to MEMORY_ROOT by default,
# namespaced for the other search roots. Kept disjoint because the wiki and the
# workspace each contain a "memory" directory, so bare relative paths would collide.
WIKI_PREFIX = "wiki/"
WORKSPACE_PREFIX = "workspace/"


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
        memory_root_exists = False
    else:
        memory_root_exists = True
    roots: list[Path] = []
    s = (scope or "all").lower()
    if s in {"all", "campaign"}:
        roots.extend(_campaign_search_roots())
    if s in {"all", "sr3", "sr3_rules", "rules", "lore"}:
        if memory_root_exists:
            roots.append(MEMORY_ROOT / "lore")
            roots.append(MEMORY_ROOT / "topics")
            roots.append(MEMORY_ROOT / "00_sources" / "rules_references")
    if memory_root_exists and s != "campaign":
        roots.append(MEMORY_ROOT / "90_derived")

    seen = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".md":
            paths = [root]
        elif root == WORKSPACE_ROOT / "memory":
            paths = (
                p for p in root.rglob("*.md")
                if DATE_NOTE_RE.fullmatch(p.name)
            )
        else:
            paths = root.rglob("*.md")
        for p in paths:
            rp = str(p.resolve())
            if rp in seen:
                continue
            seen.add(rp)
            yield p


def _campaign_search_roots() -> list[Path]:
    roots: list[Path] = []
    dossier = WORKSPACE_ROOT / "PARTY_DOSSIER.md"
    workspace_memory = WORKSPACE_ROOT / "memory"
    if dossier.exists():
        roots.append(dossier)
    if CAMPAIGN_WIKI_ROOT.exists():
        roots.append(CAMPAIGN_WIKI_ROOT)
    if workspace_memory.exists():
        roots.append(workspace_memory)
    mounted_campaign = MEMORY_ROOT / "campaign"
    if SCAN_MOUNTED_CAMPAIGN and mounted_campaign.exists():
        roots.append(mounted_campaign)
    return roots


def _doc_id(p: Path) -> str:
    for root, prefix in (
        (MEMORY_ROOT, ""),
        (CAMPAIGN_WIKI_ROOT, WIKI_PREFIX),
        (WORKSPACE_ROOT, WORKSPACE_PREFIX),
    ):
        try:
            return prefix + p.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            continue
    return p.name


def _snippet(text: str, idx: int, span: int = 220) -> str:
    if idx < 0:
        return text[:span].replace("\n", " ").strip()
    start = max(0, idx - span // 3)
    end = min(len(text), idx + span)
    return text[start:end].replace("\n", " ").strip()


_WORD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _term_count(low_text: str, term: str) -> int:
    """Whole-word occurrences only.

    Plain str.count() matched substrings, so a query for "Tom Erlichman" scored 331
    hits against the 768 KB Rigger 3 OCR blob purely on "tom" inside AUTOMOBILE /
    KINGDOM / BOTTOM, burying the actual NPCs/Tom-Erlichman.md page.
    Lookarounds rather than \\b so terms with punctuation on either end still match.
    """
    pat = _WORD_RE_CACHE.get(term)
    if pat is None:
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")
        _WORD_RE_CACHE[term] = pat
    return len(pat.findall(low_text))


def keyword_search(query: str, scope: str = "all", limit: int = 8) -> list[SearchHit]:
    q = (query or "").strip()
    if not q:
        return []

    terms = [t for t in re.split(r"\s+", q.lower()) if t]
    candidates: list[tuple[Path, str, list[int], int]] = []

    for doc in _iter_docs(scope):
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        low = text.lower()
        counts = [_term_count(low, t) for t in terms]
        if not any(counts):
            continue
        candidates.append((doc, text, counts, low.find(terms[0])))

    if not candidates:
        return []

    # Smooth IDF over the candidate set. log((1+N)/(1+df)) goes to 0 for a term that
    # appears in every document, so filler such as "who"/"is"/"the" drops out; a
    # distinctive surname such as "erlichman" carries the ranking.
    n_docs = len(candidates)
    idf = [
        math.log((1.0 + n_docs) / (1.0 + sum(1 for _, _, c, _ in candidates if c[i] > 0)))
        for i in range(len(terms))
    ]

    hits: list[SearchHit] = []
    for doc, text, counts, first_idx in candidates:
        # Saturating tf: without this a 1.4 MB rulebook with 1500 incidental mentions
        # of a filler word outranks a 12 KB NPC page that is about the thing asked.
        tf = [1.0 + math.log(c) if c > 0 else 0.0 for c in counts]
        # Length normalisation: a multi-megabyte OCR dump must not outrank a short
        # page on raw term frequency alone.
        norm = 1.0 + math.log10(max(1.0, len(text) / 4000.0))
        score = sum(t * w for t, w in zip(tf, idf)) / norm
        # Filename is a strong intent signal (NPC / host / topic pages are named
        # after the thing being asked about).
        stem = re.sub(r"[^a-z0-9]+", " ", doc.stem.lower())
        score += sum(w * 3.0 for t, w in zip(terms, idf) if t in stem)
        hits.append(
            SearchHit(
                doc_id=_doc_id(doc),
                filename=doc.name,
                score=float(round(score, 3)),
                snippet=_snippet(text, first_idx),
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: max(1, min(limit, 30))]


def semantic_search(query: str, scope: str = "all", limit: int = 8) -> list[SearchHit]:
    # Fallback semantic mode: keyword retrieval until embedding index endpoint is wired.
    return keyword_search(query=query, scope=scope, limit=limit)


def get_doc(doc_id: str, max_chars: int = 8000) -> dict:
    doc_id = (doc_id or "").strip().lstrip("/")
    if doc_id.startswith(WIKI_PREFIX):
        base, rel = CAMPAIGN_WIKI_ROOT, doc_id[len(WIKI_PREFIX):]
    elif doc_id.startswith(WORKSPACE_PREFIX):
        base, rel = WORKSPACE_ROOT, doc_id[len(WORKSPACE_PREFIX):]
    else:
        base, rel = MEMORY_ROOT, doc_id

    p = (base / rel).resolve()
    root_resolved = str(base.resolve())
    if str(p) != root_resolved and not str(p).startswith(root_resolved + os.sep):
        raise ValueError("doc_id outside permitted roots")

    if not p.exists() or not p.is_file():
        # Agents commonly guess a bare filename from a search hit; resolve by name so
        # a follow-up read costs one round trip instead of a re-search.
        needle = Path(rel).as_posix()
        for cand in _iter_docs("all"):
            cand_posix = cand.as_posix()
            if cand.name == Path(needle).name or cand_posix.endswith("/" + needle):
                p = cand.resolve()
                break

    if not p.exists() or not p.is_file():
        raise FileNotFoundError(doc_id)

    text = p.read_text(encoding="utf-8", errors="replace")
    return {
        "doc_id": doc_id,
        "filename": p.name,
        "path": str(p),
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
