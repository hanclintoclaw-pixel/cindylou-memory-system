#!/usr/bin/env python3
"""Build a private fast-lookup cache from finsterdexter/sr3data.

This imports structured NSRCG-derived SR3 data into the local data tier. It does
not publish the dataset into the campaign wiki or cleaned memory corpus.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths


DEFAULT_REPO_URL = "https://github.com/finsterdexter/sr3data.git"
DEFAULT_CACHE_DIR = get_paths().cache_root / "sr3data"
DATASET_FILES = {
    "adept_powers": "adept_powers.json",
    "bioware": "bioware.json",
    "contacts": "contacts.json",
    "critter_powers": "critter_powers.json",
    "critter_weaknesses": "critter_weaknesses.json",
    "cyberware": "cyberware.json",
    "decks": "decks.json",
    "edges_flaws": "edges_flaws.json",
    "gear": "gear.json",
    "magegear": "magegear.json",
    "skills": "skills.json",
    "spells": "spells.json",
    "totems": "totems.json",
    "vehicles": "vehicles.json",
}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def ensure_source(repo_url: str, source_dir: Path, refresh: bool) -> str:
    source_dir.parent.mkdir(parents=True, exist_ok=True)
    if source_dir.exists() and refresh:
        shutil.rmtree(source_dir)
    if not source_dir.exists():
        run(["git", "clone", "--depth", "1", repo_url, str(source_dir)])
    elif (source_dir / ".git").exists():
        run(["git", "pull", "--ff-only"], cwd=source_dir)
    return run(["git", "rev-parse", "HEAD"], cwd=source_dir)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_book_code(raw: str | None) -> tuple[str, str]:
    if not raw:
        return "", ""
    value = raw.strip()
    if "." in value:
        book, page = value.split(".", 1)
        return book.strip().lower(), page.strip()
    return value.strip().lower(), ""


def classify_source(book_code: str, book_map: dict[str, dict[str, Any]]) -> str:
    if not book_code:
        return "unknown"
    book = book_map.get(book_code)
    name = str(book.get("name", "")).lower() if book else ""
    if book_code == "cus" or "custom" in name:
        return "custom"
    if book_code.startswith("cb") or "cyberpunk" in name or "conversion" in name:
        return "conversion"
    if book_code in {"sr1", "sr2", "ssc", "fof", "awk", "ct", "st", "gm2", "r2", "rbb"} or "1st ed" in name or "2nd ed" in name:
        return "legacy"
    if book_code == "tss" or "supplemental" in name:
        return "supplemental"
    if book and book.get("load_as_default"):
        return "sr3_default"
    if book:
        return "sr3_optional"
    return "unknown"


def compact_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(compact_value(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {compact_value(val)}" for key, val in value.items())
    return str(value)


def normalize_record(dataset: str, index: int, raw: dict[str, Any], book_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    book_code, page = normalize_book_code(raw.get("Book.Page") or raw.get("book"))
    if not page and raw.get("page"):
        page = str(raw.get("page", "")).strip()
    book = book_map.get(book_code, {})
    category = raw.get("category_tree") or raw.get("skill_class") or raw.get("Category") or []
    if isinstance(category, str):
        category_path = category
    else:
        category_path = " > ".join(str(part) for part in category if str(part).strip())
    name = str(raw.get("name") or raw.get("Name") or f"{dataset} #{index + 1}").strip()
    source_kind = classify_source(book_code, book_map)
    search_parts = [dataset, name, category_path, book_code, str(book.get("name", "")), page]
    for key, value in raw.items():
        if key in {"name", "Name", "category_tree", "skill_class", "Book.Page", "book", "page"}:
            continue
        search_parts.append(str(key))
        search_parts.append(compact_value(value))
    return {
        "id": f"{dataset}:{index}",
        "dataset": dataset,
        "name": name,
        "category_path": category_path,
        "book_code": book_code,
        "book_name": book.get("name", ""),
        "page": page,
        "source_ref": f"{book_code}.{page}" if book_code and page else book_code,
        "source_kind": source_kind,
        "load_as_default": bool(book.get("load_as_default", False)),
        "fields": raw,
        "search_text": " ".join(part for part in search_parts if part),
    }


def iter_records(source_dir: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    output_dir = source_dir / "output"
    book_entries = load_json(output_dir / "books.json")
    book_map = {str(entry["abbreviation"]).lower(): entry for entry in book_entries}
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for dataset, filename in DATASET_FILES.items():
        items = load_json(output_dir / filename)
        if not isinstance(items, list):
            raise TypeError(f"Expected list in {filename}")
        counts[dataset] = len(items)
        for index, raw in enumerate(items):
            if not isinstance(raw, dict):
                continue
            records.append(normalize_record(dataset, index, raw, book_map))
    return records, counts


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_sqlite(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE records (
              id TEXT PRIMARY KEY,
              dataset TEXT NOT NULL,
              name TEXT NOT NULL,
              category_path TEXT,
              book_code TEXT,
              book_name TEXT,
              page TEXT,
              source_ref TEXT,
              source_kind TEXT,
              load_as_default INTEGER,
              fields_json TEXT NOT NULL,
              search_text TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE VIRTUAL TABLE records_fts USING fts5(id UNINDEXED, name, dataset, category_path, source_ref, search_text)")
        rows = [
            (
                rec["id"], rec["dataset"], rec["name"], rec["category_path"], rec["book_code"],
                rec["book_name"], rec["page"], rec["source_ref"], rec["source_kind"],
                int(rec["load_as_default"]), json.dumps(rec["fields"], ensure_ascii=False, sort_keys=True),
                rec["search_text"],
            )
            for rec in records
        ]
        conn.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.executemany(
            "INSERT INTO records_fts (id, name, dataset, category_path, source_ref, search_text) VALUES (?, ?, ?, ?, ?, ?)",
            [(rec["id"], rec["name"], rec["dataset"], rec["category_path"], rec["source_ref"], rec["search_text"]) for rec in records],
        )
        conn.execute("CREATE INDEX idx_records_dataset ON records(dataset)")
        conn.execute("CREATE INDEX idx_records_source_kind ON records(source_kind)")
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build private local SQLite/JSONL cache from sr3data")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--refresh-source", action="store_true", help="delete/reclone source snapshot before importing")
    args = parser.parse_args()

    source_dir = args.cache_dir / "source"
    imported_at = int(time.time())
    commit = ensure_source(args.repo_url, source_dir, args.refresh_source)
    records, counts = iter_records(source_dir)
    jsonl_path = args.cache_dir / "normalized_records.jsonl"
    db_path = args.cache_dir / "sr3data.sqlite"
    write_jsonl(records, jsonl_path)
    write_sqlite(records, db_path)
    manifest = {
        "source": "finsterdexter/sr3data",
        "repo_url": args.repo_url,
        "commit": commit,
        "imported_at": imported_at,
        "record_count": len(records),
        "dataset_counts": counts,
        "outputs": {"jsonl": str(jsonl_path), "sqlite": str(db_path)},
        "policy": "Private local tooling cache; do not publish raw dataset into campaign wiki without rights review.",
    }
    manifest_path = args.cache_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
