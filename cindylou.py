#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import importlib.util

_bridge_path = REPO_ROOT / "05_serving" / "memory_bridge.py"
_spec = importlib.util.spec_from_file_location("memory_bridge", _bridge_path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load memory bridge module: {_bridge_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

get_doc = _mod.get_doc
keyword_search = _mod.keyword_search
semantic_search = _mod.semantic_search
upsert_fact = _mod.upsert_fact
queue_entity = _mod.queue_entity
rebuild = _mod.rebuild
restart = _mod.restart


def cmd_search(args):
    fn = semantic_search if args.type == "semantic" else keyword_search
    hits = fn(query=args.q, scope=args.scope, limit=args.limit)
    print(
        json.dumps(
            {
                "query": args.q,
                "type": args.type,
                "scope": args.scope,
                "results": [h.__dict__ for h in hits],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_get(args):
    print(json.dumps(get_doc(args.doc_id, max_chars=args.max_chars), ensure_ascii=False, indent=2))


def cmd_rules_answer(args):
    """Page-level SR3 rules retrieval with an explicit accept/decline.

    Separate from `search` because the contract is different. `search` returns a ranked
    list and leaves the caller to decide what is good enough, which is how a whole-book
    hit on "pistol" ended up speaking typesetting credits as a damage ruling. This returns
    a decision: accepted is true only when at least `min_books` distinct rulebooks carry
    the asked-about term inside the excerpt that would actually be read aloud.
    """
    allow = tuple(t.strip() for t in args.shape_allow.split(",") if t.strip()) or None
    ans = _mod.page_answer(
        query=args.q,
        limit=args.limit,
        min_responsive_books=args.min_books,
        shape_allowlist=allow,
    )
    print(
        json.dumps(
            {
                "query": args.q,
                "accepted": ans.accepted,
                "reason": ans.reason,
                "responsive_books": ans.responsive_books,
                "pages": [
                    {
                        "book": h.book,
                        "section": h.section,
                        "citation": h.citation(),
                        "printed_page": h.printed_page,
                        "printed_source": h.printed_source,
                        "marker_page": h.marker_page,
                        "score": h.score,
                        "ruling_shape": h.ruling_shape,
                        "ruling_hits": h.ruling_hits,
                        "excerpt_source": h.excerpt_source,
                        "subject": h.subject,
                        "doc_id": h.doc_id,
                        "excerpt": h.snippet[: args.max_chars],
                    }
                    for h in ans.hits[: args.limit]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _read_json_arg(args):
    if args.json:
        return json.loads(args.json)
    if args.json_file:
        return json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    raise SystemExit("Provide --json or --json-file")


def cmd_upsert_fact(args):
    payload = _read_json_arg(args)
    print(json.dumps(upsert_fact(payload), ensure_ascii=False, indent=2))


def cmd_queue_entity(args):
    payload = _read_json_arg(args)
    print(json.dumps(queue_entity(payload), ensure_ascii=False, indent=2))


def cmd_rebuild(args):
    print(json.dumps(rebuild(target=args.target or "", scope=args.scope), ensure_ascii=False, indent=2))


def cmd_restart(args):
    print(json.dumps(restart(service=args.service, wiki_port=args.wiki_port, api_port=args.api_port), ensure_ascii=False, indent=2))


def build_parser():
    p = argparse.ArgumentParser(prog="cindylou", description="Cindy Lou memory bridge CLI")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="keyword or semantic search")
    s.add_argument("--q", required=True, help="query text")
    s.add_argument("--type", choices=["keyword", "semantic"], default="keyword")
    s.add_argument("--scope", default="all", help="all|campaign|sr3_rules")
    s.add_argument("--limit", type=int, default=8)
    s.set_defaults(func=cmd_search)

    ra = sub.add_parser(
        "rules-answer",
        help="page-level SR3 rules retrieval with an accept/decline decision",
    )
    ra.add_argument("--q", required=True, help="rules question, in the asker's words")
    ra.add_argument("--limit", type=int, default=4)
    ra.add_argument(
        "--min-books",
        type=int,
        default=2,
        help="distinct rulebooks that must independently carry the ruling (default 2)",
    )
    ra.add_argument("--max-chars", type=int, default=900)
    ra.add_argument(
        "--shape-allow",
        default="",
        help="comma-separated ruling shapes to accept (e.g. attribute_link,damage_code); "
        "empty allows any shape. Pages with no shape are declined when set.",
    )
    ra.set_defaults(func=cmd_rules_answer)

    g = sub.add_parser("get", help="get document by doc_id")
    g.add_argument("doc_id")
    g.add_argument("--max-chars", type=int, default=8000)
    g.set_defaults(func=cmd_get)

    u = sub.add_parser("upsert-fact", help="write fact JSON")
    u.add_argument("--json")
    u.add_argument("--json-file")
    u.set_defaults(func=cmd_upsert_fact)

    q = sub.add_parser("queue-entity", help="append entity queue request JSON")
    q.add_argument("--json")
    q.add_argument("--json-file")
    q.set_defaults(func=cmd_queue_entity)

    r = sub.add_parser("rebuild", help="rebuild campaign memory artifacts")
    r.add_argument("--target", help="optional entity target name")
    r.add_argument("--scope", choices=["all", "campaign", "entity"], default="all")
    r.set_defaults(func=cmd_rebuild)

    rs = sub.add_parser("restart", help="restart memory-system local services")
    rs.add_argument("--service", choices=["all", "wiki", "api"], default="all")
    rs.add_argument("--wiki-port", type=int, default=8889)
    rs.add_argument("--api-port", type=int, default=8091)
    rs.set_defaults(func=cmd_restart)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
