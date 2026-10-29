#!/usr/bin/env python3
"""Fill the SR3 corpus from native PDF text layers, page by page, without regressions.

Born from the 2026-10-28 audit follow-up. The five Tier-1 books have real text layers,
so native extraction is strictly more accurate than their OCR (page 1 of the Core
Rulebook reads "Gavin Lowi lorder #24266" in the corpus where the PDF says
"Gavin Lowry (order #24266)"). It is NOT strictly more complete, which is the trap:
these FanPro PDFs are hybrids, text-layer on most pages and image-only on others, and
on the image-only pages OCR already scraped text that the native layer simply does not
have. Measured before writing this tool:

    book                          corpus  native  empty(corpus->native)  pages thinner
    SR3_Core_Rulebook_FanPro      1403390 1430195        15 -> 0              2
    SR3_Magic_in_the_Shadows      752043   751646         0 -> 0              0
    SR3_System_Failure            577045   578133         4 -> 10             7
    SR3_Critters                  177607   192997         0 -> 1              2
    SR3_Matrix                    638775   672460         7 -> 17            15

A whole-file replace would therefore have blanked 10 System Failure pages and 15 Matrix
pages that currently carry readable text, in exchange for filling 10 and 7. Net loss.

So the unit of work is the page, and the rule is: adopt native text only where it is at
least THRESHOLD * corpus length, or where the corpus page is empty and native is not.
Both halves matter. The first is what stops a hybrid PDF from deleting a page; the
second is what fills the 22 empty Core Rulebook bodies that motivated this in the first
place. Volume is a proxy, not truth - a long column-bleed page stays OCR'd. Pages that
keep OCR despite native text existing are counted as kept_corpus_thin and reported, so
the number of accepted imperfections is visible rather than buried.

Safety: whole-file backup plus a JSONL change log under the sanctioned intermediates
tier, matching ocr_repair.py. Audit mode writes nothing. The writer preserves any text
preceding the first page marker (frontmatter) even though the current corpus has none,
and refuses a book whose page count does not line up with the PDF.

Usage:
  native_reextract.py audit                 # report only, write nothing
  native_reextract.py apply                 # back up, rewrite, log
  native_reextract.py audit --book SR3_Matrix_7909
  native_reextract.py apply --threshold 0.85
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pypdf  # noqa: F401  (import guard below gives a cleaner message)

logging.getLogger("pypdf").setLevel(logging.ERROR)

CORPUS = Path("/Volumes/carbonite/claw/data/cindylou/cleaned/memory/00_sources/rules_references")
LIB = Path("/Volumes/carbonite/GDrive/cindylou/Shadowrun_3e_Rules_Library/organized_3e")
STAGING = Path("/Volumes/carbonite/claw/data/cindylou/intermediates/native-reextract")

# The five books the 2026-10-28 audit confirmed carry a native text layer.
# SR3_Matrix_FASA7909 is deliberately absent: it is byte-identical to SR3_Matrix_7909
# and is queued for de-duplication, so extracting it twice would just duplicate drift.
TIER1 = [
    ("core_rules", "SR3_Core_Rulebook_FanPro"),
    ("sourcebooks", "SR3_Magic_in_the_Shadows_FanPro"),
    ("sourcebooks", "SR3_System_Failure_FanPro25014"),
    ("sourcebooks", "SR3_Critters_FASA7002"),
    ("sourcebooks", "SR3_Matrix_7909"),
]

MARKER = re.compile(r"^===== PAGE (\d+) =====$", re.M)
EMPTY_AT = 5  # below this a page body counts as empty, matching the audit's definition


def split_pages(text: str):
    """Return (prefix, [(page_number, body), ...]) preserving order."""
    parts = MARKER.split(text)
    prefix = parts[0]
    pairs = [(int(parts[i]), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    return prefix, pairs


def render_pages(prefix: str, pairs) -> str:
    out = [prefix]
    for num, body in pairs:
        out.append(f"===== PAGE {num} =====\n{body}")
        if not body.endswith("\n"):
            out.append("\n")
    return "".join(out)


def native_pages(pdf: Path):
    from pypdf import PdfReader

    return [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]


def plan_book(sub: str, name: str, threshold: float):
    """Decide every page. Returns (new_text_or_None, stats) and never mutates."""
    src = CORPUS / sub / name / "source.md"
    pdf = LIB / sub / f"{name}.pdf"
    st: Counter = Counter()
    if not src.is_file():
        st["missing_corpus"] += 1
        return None, st
    if not pdf.is_file():
        st["missing_pdf"] += 1
        return None, st

    text = src.read_text(encoding="utf-8")
    prefix, pairs = split_pages(text)
    pages = native_pages(pdf)
    st["pages_corpus"] = len(pairs)
    st["pages_pdf"] = len(pages)

    # Page numbering must line up marker-for-page or every substitution below is
    # silently writing the wrong page's text into the corpus.
    nums = [n for n, _ in pairs]
    if nums != list(range(1, len(pages) + 1)):
        st["alignment_mismatch"] += 1
        return None, st

    changed: list[tuple[int, str]] = []
    for idx, (num, body) in enumerate(pairs):
        nat = pages[idx]
        cb, nb = len(body.strip()), len(nat.strip())
        if nb < EMPTY_AT:
            st["native_empty"] += 1
            continue
        if cb < EMPTY_AT:
            changed.append((num, nat))
            st["gap_filled"] += 1
            continue
        if nb >= threshold * cb:
            if nat.strip() != body.strip():
                changed.append((num, nat))
                st["native_adopted"] += 1
            else:
                st["identical"] += 1
        else:
            # Native exists but is too thin to trust as a replacement.
            st["kept_corpus_thin"] += 1
            if nb > cb:
                st["kept_though_native_longer"] += 1

    if not changed:
        return None, st
    # Guard the property the whole design rests on: no page goes from non-empty to empty.
    rebuilt = render_pages(prefix, [(n, dict(changed).get(n, b)) for n, b in pairs])
    _, after = split_pages(rebuilt)
    for (n, b), (n0, b0) in zip(after, pairs):
        if len(b0.strip()) >= EMPTY_AT and len(b.strip()) < EMPTY_AT:
            st["aborted_would_empty_page"] += 1
            return None, st
    return rebuilt, st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["audit", "apply"])
    ap.add_argument("--book", help="limit to one book directory name")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="adopt native only when it is at least this * corpus length")
    args = ap.parse_args()
    if args.threshold <= 0 or args.threshold > 2:
        print("threshold must be in (0, 2]", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.mode == "apply":
        (STAGING / stamp / "backup").mkdir(parents=True, exist_ok=True)

    hdr = (f"{'book':<32}{'pages':>6}{'filled':>7}{'adopt':>7}{'keepthin':>9}"
           f"{'same':>6}{'nativEmpty':>11}{'chars+':>9}")
    print(hdr)
    grand: Counter = Counter()
    wrote = 0
    for sub, name in TIER1:
        if args.book and args.book != name:
            continue
        new, st = plan_book(sub, name, args.threshold)
        grand.update(st)
        delta = 0
        if new is not None:
            old_len = len((CORPUS / sub / name / "source.md").read_text(encoding="utf-8"))
            delta = len(new) - old_len
        print(f"{name:<32}{st['pages_corpus']:>6}{st['gap_filled']:>7}{st['native_adopted']:>7}"
              f"{st['kept_corpus_thin']:>9}{st['identical']:>6}{st['native_empty']:>11}"
              f"{delta:>+9}")
        if new is not None and args.mode == "apply":
            src = CORPUS / sub / name / "source.md"
            bak = STAGING / stamp / "backup" / f"{sub}--{name}--source.md"
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, bak)
            src.write_text(new, encoding="utf-8")
            with (STAGING / stamp / "changes.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "book": name, "corpus": str(src), "backup": str(bak),
                    "threshold": args.threshold, "changed_pages": st["gap_filled"] + st["native_adopted"],
                    "gap_filled": st["gap_filled"], "native_adopted": st["native_adopted"],
                    "kept_corpus_thin": st["kept_corpus_thin"], "char_delta": delta,
                    "stamp": stamp,
                }) + "\n")
            wrote += 1

    print(f"\nmode={args.mode} threshold={args.threshold} books_written={wrote}")
    for k in ("gap_filled", "native_adopted", "kept_corpus_thin", "kept_though_native_longer",
              "native_empty", "identical", "alignment_mismatch", "aborted_would_empty_page",
              "missing_corpus", "missing_pdf"):
        if grand[k]:
            print(f"  {k:<28}{grand[k]}")
    if args.mode == "apply" and wrote:
        print(f"  backups + changes.jsonl -> {STAGING / stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
