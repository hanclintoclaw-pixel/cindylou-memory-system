#!/usr/bin/env python3
"""Fast local lookup for the private sr3data SQLite cache."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths


DEFAULT_DB = get_paths().cache_root / "sr3data" / "sr3data.sqlite"
DATASETS = [
    "adept_powers", "bioware", "contacts", "critter_powers", "critter_weaknesses",
    "cyberware", "decks", "edges_flaws", "gear", "magegear", "skills", "spells",
    "totems", "vehicles",
]
SOURCE_KINDS = ["sr3_default", "sr3_optional", "legacy", "conversion", "supplemental", "custom", "unknown"]


def fts_query(text: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+", text.lower())
    if not terms:
        raise SystemExit("Query must contain at least one searchable word")
    return " AND ".join(f"{term}*" for term in terms)


def lookup(args: argparse.Namespace) -> list[dict[str, object]]:
    if not args.db.exists():
        raise SystemExit(f"Cache DB not found: {args.db}\nRun scripts/import_sr3data_cache.py first.")
    where = ["records_fts MATCH ?"]
    params: list[object] = [fts_query(args.query)]
    if args.dataset:
        where.append("r.dataset = ?")
        params.append(args.dataset)
    if args.source_kind:
        where.append("r.source_kind = ?")
        params.append(args.source_kind)
    sql = f"""
      SELECT r.id, r.dataset, r.name, r.category_path, r.book_code, r.book_name, r.page,
             r.source_ref, r.source_kind, r.load_as_default, r.fields_json,
             bm25(records_fts) AS rank
      FROM records_fts
      JOIN records r ON r.id = records_fts.id
      WHERE {' AND '.join(where)}
      ORDER BY rank, r.dataset, r.name
      LIMIT ?
    """
    params.append(args.limit)
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    results = []
    for row in rows:
        fields = json.loads(row["fields_json"])
        results.append(
            {
                "id": row["id"],
                "dataset": row["dataset"],
                "name": row["name"],
                "category_path": row["category_path"],
                "source": {
                    "ref": row["source_ref"],
                    "book_code": row["book_code"],
                    "book_name": row["book_name"],
                    "page": row["page"],
                    "kind": row["source_kind"],
                    "load_as_default": bool(row["load_as_default"]),
                },
                "fields": fields,
            }
        )
    return results


def print_text(results: list[dict[str, object]]) -> None:
    if not results:
        print("No matches.")
        return
    for idx, result in enumerate(results, 1):
        source = result["source"]
        assert isinstance(source, dict)
        print(f"{idx}. {result['name']} [{result['dataset']}] -- {source.get('ref') or 'no source'} ({source.get('kind')})")
        if result.get("category_path"):
            print(f"   Category: {result['category_path']}")
        fields = result["fields"]
        assert isinstance(fields, dict)
        summary_keys = [key for key in fields.keys() if key not in {"name", "category_tree", "Book.Page", "book", "page"}]
        shown = []
        for key in summary_keys[:8]:
            value = fields[key]
            if value in ("", None, [], {}):
                continue
            shown.append(f"{key}: {value}")
        if shown:
            print(f"   {'; '.join(shown)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search private sr3data cache")
    parser.add_argument("query")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dataset", choices=DATASETS)
    parser.add_argument("--source-kind", choices=SOURCE_KINDS)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = lookup(args)
    if args.json:
        print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))
    else:
        print_text(results)


if __name__ == "__main__":
    main()
