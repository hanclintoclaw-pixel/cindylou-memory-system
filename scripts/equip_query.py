#!/usr/bin/env python3
"""Trust-tiered equipment lookup for live Shadowrun 3e answers.

Wraps the private sr3data SQLite cache with an edition/provenance gate. The
underlying NSRCG-derived dataset mixes editions freely (Shadowrun 1E/2E,
Cyberpunk 2020 conversions, Raygun's Firearms, Chrome Book conversions), and
its plain-text dump returns those as top hits. This tool refuses to present
non-SR3 data as rules fact.

Tiers, strongest first:
  VERIFIED    stats corroborated against the native text layer of the citing PDF
  SR3         SR3-era source with a usable page reference
  WEAK        SR3-era source but the page reference is missing/placeholder
  QUARANTINED 2E/1E, conversion, or unknown provenance -- never voiced silently

Design rule: fail LOUD, not quiet. If every match is quarantined, the tool says
so and names the reason instead of going silent or quoting 2nd-edition numbers.

Usage:
  equip_query.py "Ares Predator"
  equip_query.py "frag grenade" --explain
  equip_query.py kevlar --strict --dataset gear
  equip_query.py "Monofilament Whip" --json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# pypdf screams about unembeddable CFF Type1 fonts on every page of these
# FanPro PDFs. The extraction is fine; the noise would bury the answer.
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("PyPDF2").setLevel(logging.ERROR)
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

DB_PATH = get_paths().cache_root / "sr3data" / "sr3data.sqlite"
PDF_ROOT = get_paths().raw_root / "Shadowrun_3e_Rules_Library" / "organized_3e"
PAGE_CACHE = get_paths().cache_root / "sr3data" / "pdf_page_text.json"

DATASETS = [
    "gear", "cyberware", "bioware", "decks", "vehicles",
    "magegear", "spells", "edges_flaws", "skills", "critter_powers",
    "adept_powers", "contacts", "totems",
]

# Books whose PDFs carry a genuine text layer (measured 2026-10-28: 5 of 29
# books in the library are non-scans). Only these can promote a row to VERIFIED.
TEXT_LAYER_PDFS: dict[str, list[str]] = {
    "sr3": ["core_rules/SR3_Core_Rulebook_FanPro.pdf"],
    "mits": ["sourcebooks/SR3_Magic_in_the_Shadows_FanPro.pdf"],
    "mat": [
        "sourcebooks/SR3_Matrix_7909.pdf",
        "sourcebooks/SR3_Matrix_FASA7909.pdf",
    ],
}

# Rows whose page citation points at one of these books can be verified.
VERIFIABLE_CODES = set(TEXT_LAYER_PDFS)

TIER_ORDER = ["VERIFIED", "SR3", "WEAK", "QUARANTINED"]

# SR3-era but not an official rules source: The Shadowrun Supplemental was a
# fan-produced magazine. Legal for the table only if the GM allows it, so it
# gets a visible marker instead of being silently treated like the BBB.
FAN_ERA_CODES = {"tss", "nagee", "nagee7", "nagee4-72", "bjf", "ray"}

# Fields worth voicing, in reading order. Anything else is noise.
FIELD_ORDER = [
    "Damage", "Mode", "Ammunition", "Concealability", "Reach", "Str.Min.",
    "Ballistic", "Impact", "EssCost", "BioIndex", "Capacity",
    "MPCP", "Persona", "Hardening", "Body", "Armor", "Speed", "Handling",
    "Pilot/Sensor", "Weight", "$Cost", "Availability", "Street Index", "Legal",
    "LegalCode", "Accessories", "Notes",
]


@dataclass
class Hit:
    name: str
    dataset: str
    category: str
    book_code: str
    page: str
    source_kind: str
    fields: dict[str, Any]
    tier: str = "QUARANTINED"
    cite: str = ""
    why: str = ""
    verified_tokens: list[str] = field(default_factory=list)
    missing_tokens: list[str] = field(default_factory=list)


def norm(text: str) -> str:
    """Fold text for token comparison: lowercase, squeeze punctuation runs."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def usable_page(page: str) -> bool:
    p = (page or "").strip()
    if not p or "?" in p:
        return False
    if p.lower() in {"n/a", "none", "-", "--"}:
        return False
    # 'ray.000' style placeholders carry no locatable page number.
    return any(ch.isdigit() and ch != "0" for ch in p)


def base_tier(source_kind: str, page: str) -> tuple[str, str]:
    """Tier from provenance alone, before PDF corroboration."""
    if source_kind in {"legacy", "conversion", "custom", "unknown"}:
        label = {
            "legacy": "pre-SR3 edition data",
            "conversion": "cross-system conversion",
            "custom": "fan/custom entry",
            "unknown": "unresolvable source book",
        }[source_kind]
        return "QUARANTINED", f"{label} ({source_kind})"
    if not usable_page(page):
        return "WEAK", "SR3-era source but page reference is missing/placeholder"
    return "SR3", "SR3-era source with page reference"


def stat_tokens(fields: dict[str, Any]) -> list[str]:
    """Stats worth corroborating: damage and price are the load-bearing ones."""
    out = []
    for key in ("Damage", "$Cost", "Availability", "Concealability", "EssCost"):
        val = str(fields.get(key) or "").strip()
        if val and val not in {"-", "--", "None"}:
            out.append((key, val))
    return out


def load_page_cache() -> dict[str, list[str]]:
    if PAGE_CACHE.exists():
        try:
            return json.loads(PAGE_CACHE.read_text())
        except Exception:
            pass
    return {}


def save_page_cache(cache: dict[str, list[str]]) -> None:
    """Persist extracted page text so queries after the first are instant."""
    try:
        PAGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = PAGE_CACHE.with_suffix(PAGE_CACHE.suffix + ".tmp")
        tmp.write_text(json.dumps(cache))
        tmp.replace(PAGE_CACHE)
    except Exception:
        pass  # verification degrades to SR3 tier; never break a lookup


def pdf_pages(pdf: Path, cache: dict[str, list[str]]) -> list[str] | None:
    key = str(pdf)
    if key in cache:
        return cache[key]
    if not pdf.exists():
        cache[key] = []
        return []
    try:
        from pypdf import PdfReader
    except ImportError:
        cache[key] = []
        return None
    try:
        pages = [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    except Exception:
        pages = []
    cache[key] = pages
    return pages


def find_pages(pages: list[str], needle: str, cited: int, window: int = 40) -> list[int]:
    """Pages containing the item name, preferring those near the cited page."""
    hits = [i for i, txt in enumerate(pages) if needle in norm(txt)]
    if not hits:
        return []
    return sorted(hits, key=lambda i: abs(i + 1 - cited))[:5]


def corroborate(hit: Hit, page_cache: dict[str, list[str]]) -> None:
    """Promote SR3 -> VERIFIED when the citing PDF's own text layer agrees."""
    if hit.tier not in {"SR3", "VERIFIED"}:
        return
    rels = TEXT_LAYER_PDFS.get(hit.book_code)
    if not rels:
        hit.why += "; not verifiable (book is an image scan)"
        return
    tokens = stat_tokens(hit.fields)
    if not tokens:
        hit.why += "; nothing to corroborate (no stat fields)"
        return
    name_key = norm(re.sub(r"\s*\((?:[A-Za-z0-9 .&/-]{1,14})\)\s*$", "", hit.name))
    for rel in rels:
        pages = pdf_pages(PDF_ROOT / rel, page_cache)
        if not pages:
            continue
        try:
            cited = int(re.match(r"(\d+)", hit.page).group(1))  # type: ignore[union-attr]
        except Exception:
            cited = 1
        for idx in find_pages(pages, name_key, cited):
            blob = norm(pages[idx])
            present = [k for k, v in tokens if norm(v) in blob]
            missing = [k for k, v in tokens if norm(v) not in blob]
            if len(present) >= max(2, len(tokens) - 1):
                hit.tier = "VERIFIED"
                hit.verified_tokens = present
                hit.missing_tokens = missing
                hit.cite = f"{hit.book_code}.{hit.page} -> {Path(rel).name} p.{idx + 1}"
                hit.why = (
                    f"stats {present} found on the PDF's own text layer "
                    f"(not OCR output)"
                )
                if missing:
                    hit.why += f"; {missing} not on that page"
                return
        hit.why += f"; name not located in {Path(rel).name}"


# Wake lines arrive as spoken sentences ("hey cindy what does a monofilament whip
# do"). Left in, those function words force the AND query to fail and the OR
# fallback then returns anything containing "do" or "a" - measured junk hits were
# "Ugly and Doesn't Care" and "Off-line Store 100 Mp".
STOPWORDS = frozenset("""
  a an the is are was were be been do does did doing what whats whats whats
  how much many many many does can could would should i we you your my our
  it its of on in at to for with and or but if then than that this these
  there here its im ive youre cant wont got have has had about from into
  out up down over under some any all just really very quite please tell
  give me us them him her its ok okay hey hi yo um uh like get got need
  want wanna looking looking stats stat specs spec price cost costs
  damage avail availability rate value worth read know name call called
  cindy cindylou cindyloubot cindey sindy bot
""".split())


def significant_terms(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) > 1 and t not in STOPWORDS]


# The fts5 index carries no stemmer, and queries are prefix terms (``term*``),
# so a table that the book prints one way is unreachable when the table *says*
# it the other way. Measured 2026-11-12: "suppressor" -> 0 citable rows, while
# the book's own spelling "suppresser" -> the VERIFIED core row (Silencer /
# Sound Suppresser, sr3.282). A player at the table will always say the first.
# Only the QUERY side is widened: a row still has to contain a variant of every
# term, so AND precision holds, and tiers/gates are untouched -- a widened match
# can surface a citable row, never promote a quarantined one.
_SUFFIX_VARIANTS = (("er", "or"), ("re", "er"))


def term_variants(term: str) -> list[str]:
    """Orthographic variants of one query term (suppressor <-> suppresser).

    Both directions, because the table and the book disagree in either: the
    printed core prints "Sound Suppresser", the table files it under
    "...Suppressors", and the player at the table says "suppressor". A prefix
    term (``x*``) matches longer words but never shorter ones, so the plural a
    player says cannot reach the singular row the book prints.
    """
    out: list[str] = []

    def add(word: str) -> None:
        if word and word not in out:
            out.append(word)

    queue = [term]
    while queue:
        w = queue.pop(0)
        add(w)
        for suffix, alt in _SUFFIX_VARIANTS:
            if w.endswith(suffix) and len(w) > len(suffix) + 2:
                cand = w[: -len(suffix)] + alt
                if cand not in out:
                    queue.append(cand)
        if w[-2:] in ("er", "or") and len(w) > 4:
            stem = w[:-2]
            for cand in (stem + "er", stem + "or"):
                if cand not in out:
                    queue.append(cand)
        if w.endswith("ies") and len(w) > 4:
            queue.append(w[:-3] + "y")
        elif w.endswith("es") and len(w) > 4:
            # "grenades" -> "grenade" (drop -s) and "boxes" -> "box" (drop -es);
            # a prefix term matches longer words only, so the singular the book
            # prints is otherwise unreachable from the plural a player says.
            queue.append(w[:-1])
            queue.append(w[:-2])
        elif w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
            queue.append(w[:-1])
        if len(out) >= 8:
            break
    return out[:8]


def fts_query(text: str, mode: str = "and") -> str:
    terms = significant_terms(text)
    if not terms:
        raise SystemExit("query must contain at least one searchable word")
    joiner = " AND " if mode == "and" else " OR "
    groups = []
    for t in terms:
        alts = [f"{v}*" for v in term_variants(t)]
        groups.append(alts[0] if len(alts) == 1 else "(" + " OR ".join(alts) + ")")
    return joiner.join(groups)


def name_overlap(query: str, name: str) -> int:
    """How many significant query terms actually appear in the row's name.

    Relevance floor for the OR fallback: a row whose name shares no significant
    term with the question is noise, however well it matched on Notes or a field
    value. Zero overlap means the row answers nothing the player asked. Variants
    count as the term they stand for, or a widened search would win the FTS
    round and then be thrown away here.
    """
    n = norm(name)
    return sum(1 for t in significant_terms(query)
               if any(v in n for v in term_variants(t)))


# Reference tables that answer "what is this" but are not equipment. Pulling
# them into a gear query buries the item under a skill or totem row.
NON_EQUIPMENT_DATASETS = {
    "skills", "totems", "adept_powers", "critter_powers",
    "critter_weaknesses", "contacts",
}


def is_mod_row(name: str) -> bool:
    """'+Chemseal' style rows are accessory add-ons, not items in themselves."""
    return name.strip().startswith("+")


def search(
    query: str,
    dataset: str | None,
    limit: int,
) -> list[Hit]:
    if not DB_PATH.exists():
        raise SystemExit(f"cache DB not found: {DB_PATH}")
    def rows_for(match: str, mode: str, fetch: int) -> list[sqlite3.Row]:
        where = ["records_fts MATCH ?"]
        params: list[Any] = [fts_query(match, mode)]
        if dataset:
            where.append("r.dataset = ?")
            params.append(dataset)
        else:
            # Without an explicit --dataset, keep reference tables (skills,
            # totems, powers) out of the way so the item itself ranks first.
            marks = ",".join("?" for _ in NON_EQUIPMENT_DATASETS)
            where.append(f"r.dataset NOT IN ({marks})")
            params.extend(sorted(NON_EQUIPMENT_DATASETS))
        sql = f"""
          SELECT r.name, r.dataset, r.category_path, r.book_code, r.page,
                 r.source_kind, r.fields_json,
                 bm25(records_fts) AS rank
          FROM records_fts JOIN records r ON r.id = records_fts.id
          WHERE {' AND '.join(where)}
          ORDER BY rank, r.name
          LIMIT ?
        """
        # bm25 is not the ranking that decides what the player sees -- name
        # overlap and tier do, below. `fetch` is chosen by the caller: the
        # narrow window is the historical behaviour and keeps class questions
        # ("what does a cyberdeck cost") answering from the bm25 top, while the
        # wide window is a rescue -- widening the query with spelling variants
        # floods the top of the bm25 list with long fan rows (measured
        # 2026-11-12: "silencers" put 25 fan-published Raygun rows ahead of the
        # core rulebook's own Silencer, sr3.282, so a limit-25 query returned
        # zero citable rows even though the row existed).
        params.append(fetch)
        return conn.execute(sql, params).fetchall()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows: list[sqlite3.Row] = []
    alias_note = ""
    narrow = max(limit, 20)
    try:
        # First pass keeps the historical shape exactly: AND is strict and
        # trustworthy; OR is a rescue used only when AND found nothing, because OR
        # matches on Notes/field text and drags in rows whose name shares nothing
        # with the question (measured junk: "Ugly and Doesn't Care" for "Uzi III
        # cost", "Off-line Store 100 Mp" for "sandevistan"). An OR row must share
        # a significant term with the row NAME to count.
        for mode in ("and", "or"):
            cand = rows_for(query, mode, narrow)
            if mode == "or":
                cand = [r for r in cand if name_overlap(query, r["name"]) >= 1]
            if cand:
                rows = cand
                break
        # Nothing citable in the narrow window: re-run wide so a citable row that
        # bm25 buried below fan noise can still reach the re-rank. Only a rescue,
        # because the wide window also lets accessory rows (Matrix "Touchpad")
        # into a class question they should not answer.
        if rows and not any(base_tier(r["source_kind"], r["page"])[0] == "SR3" for r in rows):
            widened: list[sqlite3.Row] = []
            for mode in ("and", "or"):
                cand = rows_for(query, mode, max(limit * 12, 120))
                if mode == "or":
                    cand = [r for r in cand if name_overlap(query, r["name"]) >= 1]
                if not widened:
                    widened = cand
                if any(base_tier(r["source_kind"], r["page"])[0] == "SR3" for r in cand):
                    widened = cand
                    break
            if widened:
                rows = widened
        if not rows:
            target = alias_target(query)
            if target:
                for mode in ("and", "or"):
                    cand = rows_for(target, mode, narrow)
                    if mode == "or":
                        cand = [r for r in cand if name_overlap(target, r["name"]) >= 1]
                    if cand:
                        rows = cand
                        alias_note = (
                            f"matched via unverified brand alias "
                            f"'{query.strip()}' -> '{target}'"
                        )
                        break
    finally:
        conn.close()

    hits: list[Hit] = []
    for row in rows:
        name = re.sub(r"\s+", " ", row["name"]).strip()
        if is_mod_row(name):
            continue
        try:
            fields = json.loads(row["fields_json"])
        except Exception:
            fields = {}
        # drop empty values so the voice path never reads "Damage: None"
        fields = {
            k: v for k, v in fields.items()
            if str(v).strip() not in {"", "None", "-", "--"}
        }
        tier, why = base_tier(row["source_kind"], row["page"])
        if alias_note:
            tier = "WEAK" if tier in {"SR3", "VERIFIED"} else tier
            why = f"{alias_note}; GM must confirm the identification"
        hits.append(
            Hit(
                name=name,
                dataset=row["dataset"],
                category=row["category_path"] or "",
                book_code=(row["book_code"] or "").lower(),
                page=(row["page"] or "").strip(),
                source_kind=row["source_kind"],
                fields=fields,
                tier=tier,
                why=why,
                cite=f"{row['book_code']}.{row['page']}".strip("."),
            )
        )
    # Rank by how much of the question the name actually answers, then by tier.
    # bm25 alone ranks a Notes-text fluke above the item the player named -- and
    # after the widened fetch above, it also ranks 25 fan rows above the one
    # citable core entry. Truncation belongs here, never inside the SQL.
    # Sort is deliberately stable and adds no name key: rows already arrive in
    # deterministic (rank, name) order, and an extra alphabetical key silently
    # reorders same-overlap same-tier ties -- which evicted the class row this
    # lookup is supposed to surface for "cost of a commlink".
    hits.sort(key=lambda h: (-name_overlap(query, h.name), TIER_ORDER.index(h.tier)))
    return hits[:limit]


def fmt_fields(hit: Hit, max_fields: int = 9) -> str:
    ordered = [k for k in FIELD_ORDER if k in hit.fields]
    ordered += [k for k in hit.fields if k not in FIELD_ORDER]
    seen, parts = set(), []
    for k in ordered:
        if k in seen or k in {"name", "category_tree", "type_id"}:
            continue
        seen.add(k)
        v = str(hit.fields[k]).strip()
        v = re.sub(r"\s+", " ", v)
        if len(v) > 70:
            v = v[:67] + "..."
        parts.append(f"{k}={v}")
        if len(parts) >= max_fields:
            break
    return "; ".join(parts)


# Brand names players actually say, mapped to the entry this database carries.
# These equivalences are NOT corroborated by the local SR3 corpus (verified by
# grep on 2026-10-28), so results reached this way are labelled GM-CALL and
# must not be voiced as rules fact without the GM confirming the identification.
BRAND_ALIASES: dict[str, str] = {
    "sandevistan": "wired reflexes",
    "militech reflex": "wired reflexes",
    "datasoft": "wired reflexes",
    "smartglasses": "smartglass",
    "commlink": "cybercommlink",
    "hornet": "machine pistol",
}


def alias_target(query: str) -> str | None:
    q = norm(query)
    for brand, target in BRAND_ALIASES.items():
        if brand in q:
            return target
    return None


def neighborhood_suggestions(blocked: list[Hit], limit: int = 6) -> list[Hit]:
    """Point at citable rows in the same category as the quarantined hits.

    A quarantined row is still a map: 'Fragmentation mini-grenade' is dead 2E
    data, but its category tells us where the SR3 answer lives (Explosives >
    Grenades), and the real SR3 entry is simply named differently (Defensive /
    Offensive HE or AP). Refusing without a pointer is useless mid-session.
    """
    cats: list[str] = []
    for h in blocked:
        parts = [p.strip() for p in (h.category or "").split(">") if p.strip()]
        for depth in (2, 1):
            if len(parts) >= depth:
                key = ">".join(parts[:depth])
                if key not in cats:
                    cats.append(key)
    if not cats:
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    out: list[Hit] = []
    try:
        for cat in cats[:3]:
            rows = conn.execute(
                """SELECT name, dataset, category_path, book_code, page,
                          source_kind, fields_json FROM records
                   WHERE dataset='gear' AND category_path LIKE ?
                     AND source_kind IN ('sr3_default','sr3_optional')
                     AND page IS NOT NULL AND page <> '' AND page NOT LIKE '%?%'
                   ORDER BY CASE source_kind WHEN 'sr3_default' THEN 0 ELSE 1 END,
                            name LIMIT ?""",
                (f"{cat}%", limit * 3),
            ).fetchall()
            for row in rows:
                name = re.sub(r"\s+", " ", row["name"]).strip()
                if is_mod_row(name):
                    continue  # accessory add-ons are not table answers
                try:
                    fields = json.loads(row["fields_json"])
                except Exception:
                    fields = {}
                fields = {k: v for k, v in fields.items()
                          if str(v).strip() not in {"", "None", "-", "--"}}
                tier, why = base_tier(row["source_kind"], row["page"])
                if tier not in {"SR3", "VERIFIED"}:
                    continue  # placeholder page refs are not pointers either
                fields = {k: v for k, v in fields.items()
                          if str(v).strip() not in {"", "None", "-", "--"}}
                tier, why = base_tier(row["source_kind"], row["page"])
                out.append(Hit(
                    name=name,
                    dataset=row["dataset"], category=row["category_path"] or "",
                    book_code=(row["book_code"] or "").lower(),
                    page=(row["page"] or "").strip(), source_kind=row["source_kind"],
                    fields=fields, tier=tier,
                    why="citable neighbour of a quarantined entry",
                    cite=f"{row['book_code']}.{row['page']}",
                ))
    finally:
        conn.close()
    out.sort(key=lambda h: TIER_ORDER.index(h.tier))
    seen: set[str] = set()
    uniq = [h for h in out if not (h.name in seen or seen.add(h.name))]
    return uniq[:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description="trust-tiered SR3 equipment lookup")
    ap.add_argument("query")
    ap.add_argument("--dataset", choices=DATASETS)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--min-tier", choices=TIER_ORDER, default="WEAK",
                    help="lowest tier to display (default WEAK)")
    ap.add_argument("--strict", action="store_true",
                    help="only VERIFIED/SR3; exit 3 if none qualify")
    ap.add_argument("--explain", action="store_true",
                    help="print why each row sits in its tier")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip PDF corroboration (fast)")
    args = ap.parse_args()

    if args.strict:
        args.min_tier = "SR3"

    raw = search(args.query, args.dataset, max(args.limit, 20))
    page_cache = {} if args.no_verify else load_page_cache()
    for hit in raw:
        if not args.no_verify:
            corroborate(hit, page_cache)
        else:
            hit.why += "; PDF corroboration skipped (--no-verify)"
    if not args.no_verify and page_cache:
        save_page_cache(page_cache)

    # TIER_ORDER runs best-first, so "at least this good" means index <= cutoff.
    cutoff = TIER_ORDER.index(args.min_tier)
    shown = [h for h in raw if TIER_ORDER.index(h.tier) <= cutoff]
    shown.sort(key=lambda h: TIER_ORDER.index(h.tier))
    shown = shown[: args.limit]
    blocked = [h for h in raw if TIER_ORDER.index(h.tier) > cutoff]

    if args.json:
        print(json.dumps({
            "query": args.query,
            "returned": [h.__dict__ for h in shown],
            "blocked_count": len(blocked),
            "blocked_examples": [h.__dict__ for h in blocked[:3]],
        }, indent=2, default=str))
        if args.strict and not shown:
            raise SystemExit(3)
        return

    if not shown:
        print(f"NO SR3-GRADE MATCH for {args.query!r}")
        if blocked:
            kinds = sorted({h.source_kind for h in blocked})
            print(f"  {len(blocked)} match(es) exist but are quarantined: "
                  f"{', '.join(kinds)}")
            for h in blocked[:2]:
                print(f"    - {h.name} [{h.source_kind} {h.cite}] {h.why}")
        else:
            print("  no matches at any tier")
        sugg = neighborhood_suggestions(blocked)
        if sugg:
            print("  nearest citable SR3 entries (the rulebook may name these "
                  "differently):")
            for h in sugg:
                print(f"    -> {h.name} <{h.dataset}> {h.cite}  {fmt_fields(h, 4)}")
            print("  -> do NOT voice the quarantined numbers above")
        else:
            print("  -> do NOT voice these numbers; re-check the PDF or ask the GM")
        raise SystemExit(3 if args.strict else 0)

    if not args.strict and blocked:
        print(f"[gate] {len(blocked)} lower-tier match(es) hidden "
              f"(min-tier={args.min_tier}); use --explain to inspect")
    for h in shown:
        mark = {"VERIFIED": "[V]", "SR3": "[3]", "WEAK": "[~]", "QUARANTINED": "[!X]"}[h.tier]
        if h.book_code in FAN_ERA_CODES and h.tier != "QUARANTINED":
            mark += "[fan]"  # SR3-era but fan-published: GM permission required
        print(f"{mark} {h.name} <{h.dataset}> {h.cite}")
        if h.category:
            print(f"     {h.category}")
        print(f"     {fmt_fields(h)}")
        if args.explain:
            print(f"     why: {h.why}")
            if h.verified_tokens:
                print(f"     corroborated: {h.verified_tokens}")
    good = sum(1 for h in shown if h.tier in {"VERIFIED", "SR3"})
    fan = sum(1 for h in shown if h.book_code in FAN_ERA_CODES)
    print(f"\n{len(shown)} shown ({good} citable) | "
          f"VERIFIED=corroborated against PDF text layer"
          + (f" | {fan} fan-published, GM permission required" if fan else ""))


if __name__ == "__main__":
    main()
