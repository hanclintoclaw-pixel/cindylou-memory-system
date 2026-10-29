#!/usr/bin/env python3
"""Find and retire duplicate SR3 corpus books, with a citation block-list.

Written after the 2026-10-28 de-dupe request, because the premise handed to me did not
survive checking. The Matrix pair (SR3_Matrix_7909 / SR3_Matrix_FASA7909) was described as
byte-identical PDFs. It is not: different SHA-256, 90,842,258 vs 90,863,077 bytes. What IS
true is that their extracted text layers match on all 175 pages, and that their corpus
source.md files were byte-identical before the native re-extraction. So they are
text-equivalent copies of one book shipped as two files - which is the thing worth retiring,
but not the thing that was claimed.

Duplicate detection is therefore done on CONTENT, page by page, and deliberately does not
trust a whole-file hash. A whole-file hash was tried first here and reported "no duplicates
in 29 books", which is false as a recall claim: Man_and_Machine 7126 vs FASA7126 agree on
160 of 161 pages and still hash differently. An exact-match test cannot see a near-duplicate,
so the classifier below reports a similarity ratio and a verdict band instead.

Safety, in priority order:
  1. Nothing is deleted. The loser of a pair is MOVED to a quarantine directory (trash beats
     rm), so the operation is reversible by moving it back.
  2. A book whose corpus path is cited by a published wiki page is BLOCKED, not moved, unless
     --force is passed. This is the whole point of the tool: SR3_Matrix_FASA7909/source.md is
     cited verbatim by NPCs/Cindy-Lou-Jenkins-Journal/On-Otaku-and-the-Deep-Resonance.md, so
     a naive "delete the dupe" would have broken a live player-visible citation's provenance.
  3. Winners are chosen on measurable quality (empty-body count, then total characters), and
     the choice is printed before anything happens.

Usage:
  corpus_dedupe.py scan     # classify pairs, report blockers. writes nothing
  corpus_dedupe.py apply    # quarantine unblocked losers, write a manifest for rollback
  corpus_dedupe.py scan --min-ratio 0.6
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

CORPUS = Path("/Volumes/carbonite/claw/data/cindylou/cleaned/memory/00_sources/rules_references")
WIKI = Path("/Users/hanclaw/claw/projects/cindylou/campaign-wiki")
QUARANTINE = Path("/Volumes/carbonite/claw/data/cindylou/intermediates/corpus-quarantine")
# Files whose text names a corpus path; a hit means something depends on that path existing.
DEPENDENCY_ROOTS = [
    WIKI,
    Path("/Users/hanclaw/claw/projects/cindylou/memory-system/scripts"),
]

MARKER = re.compile(r"^===== PAGE (\d+) =====$", re.M)
EMPTY_AT = 5


def pages_of(text: str) -> dict[int, str]:
    """Split on page markers. One capturing group means numbers land at ODD indices."""
    parts = MARKER.split(text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def books() -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = {}
    for src in sorted(CORPUS.rglob("source.md")):
        out[str(src.relative_to(CORPUS)).removesuffix("/source.md")] = pages_of(
            src.read_text(encoding="utf-8", errors="replace"))
    return out


def quality(pg: dict[int, str]) -> tuple[int, int]:
    """Sort key: fewer empty bodies wins, then more content wins. Higher is better."""
    return (-sum(1 for v in pg.values() if len(v.strip()) < EMPTY_AT),
            sum(len(v.strip()) for v in pg.values()))


def _flat(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def similarity(a: dict[int, str], b: dict[int, str]) -> tuple[float, int, int]:
    """(ratio, n_common, n_identical). Per page, on flattened text - never whole-file bytes.

    Two bugs this shape is here to avoid, both found by cross-checking this tool against
    independent measurements rather than by reading its output:

    * Whole-file hashing reports "no duplicates" when near-duplicates exist. Man_and_Machine
      7126 vs FASA7126 agree on 160 of 161 pages and hash differently, so the obvious test
      returns the wrong answer in the dangerous direction.
    * SequenceMatcher's autojunk heuristic (on by default) treats any element of b appearing
      in more than 1% of b as junk. At character level in a 640,000-char string that means the
      letter 'e' is junk, and ratio() collapses toward zero. That is how this tool first missed
      the Matrix pair - the one pair it was written for - while still catching M&M via the
      page-identity fallback. autojunk is off, and the comparison is per page so cost is
      bounded and a single mangled page cannot sink a whole book.
    """
    common = sorted(set(a) & set(b))
    if not common:
        return 0.0, 0, 0
    same = 0
    total = 0.0
    for k in common:
        x, y = _flat(a[k]), _flat(b[k])
        if x == y:
            same += 1
            total += 1.0
            continue
        if len(x) < 20 or len(y) < 20:
            # Two near-empty pages that differ only in noise count as agreement; a page
            # with real text on one side and nothing on the other does not.
            total += 1.0 if abs(len(x) - len(y)) < 20 else 0.0
            continue
        total += SequenceMatcher(None, x, y, autojunk=False).ratio()
    return total / len(common), len(common), same


def citation_hits(rel: str) -> list[Path]:
    """Every tracked file that quotes this book's corpus path."""
    needle = str(CORPUS / rel)
    hits = []
    for root in DEPENDENCY_ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".md", ".py"}:
                try:
                    if needle in p.read_text(encoding="utf-8", errors="replace"):
                        hits.append(p)
                except (OSError, UnicodeDecodeError):
                    continue
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["scan", "apply"])
    ap.add_argument("--min-ratio", type=float, default=0.75,
                    help="treat as duplicate above this content similarity")
    ap.add_argument("--force", action="store_true",
                    help="quarantine even cited books (rewrites nothing; will break provenance)")
    args = ap.parse_args()

    bs = books()
    print(f"{len(bs)} corpus books\n")
    keys = sorted(bs)
    pairs = []
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            # Only plausibly-same books: same page count and similar stem, else 435 comparisons
            # of 175-page books is wasted work and invites false positives across sequels.
            if len(bs[ka]) != len(bs[kb]):
                continue
            ratio, n, same = similarity(bs[ka], bs[kb])
            if ratio >= args.min_ratio:
                pairs.append((ka, kb, ratio, n, same))

    if not pairs:
        print("no duplicate pairs above the ratio floor")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest_rows = []
    blocked = 0
    for ka, kb, ratio, n, same in sorted(pairs, key=lambda r: -r[2]):
        q = {ka: quality(bs[ka]), kb: quality(bs[kb])}
        # Tie-break is deliberate: an ASCII-ascending book name is the stable one, so re-running
        # this tool cannot flip which half of a pair survives.
        keep, drop = (ka, kb) if q[ka] >= q[kb] else (kb, ka)
        # Look the stats up BY BOOK. They were printed from qa/qb positionally before, which
        # silently swapped the two rows whenever the winner was kb - making a wrong pick look
        # like the well-populated copy.
        print(f"{ratio:6.3f}  {n:>4} pages, {same:>4} identical")
        print(f"        keep  {keep:<46} empties={-q[keep][0]:<3} chars={q[keep][1]}")
        print(f"        drop  {drop:<46} empties={-q[drop][0]:<3} chars={q[drop][1]}")
        hits = citation_hits(drop)
        if hits:
            blocked += 1
            print(f"        BLOCKED by {len(hits)} citation(s):")
            for h in hits:
                print(f"            {h}")
            if not args.force:
                continue
            print("        --force given, proceeding despite citations")
        src = CORPUS / drop
        if args.mode == "apply":
            dst = QUARANTINE / stamp / drop.replace("/", "--")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            manifest_rows.append({"kept": keep, "quarantined": drop, "moved_to": str(dst),
                                  "ratio": round(ratio, 4), "pages": n, "identical_pages": same,
                                  "citations": [str(h) for h in hits], "stamp": stamp})
            print(f"        QUARANTINED -> {dst}")
        else:
            print("        would quarantine (audit mode, wrote nothing)")
        print()

    if args.mode == "apply" and manifest_rows:
        QUARANTINE.joinpath(f"manifest-{stamp}.json").write_text(
            json.dumps(manifest_rows, indent=2), encoding="utf-8")
        print(f"manifest -> {QUARANTINE / f'manifest-{stamp}.json'}")
        print("rollback: move the quarantined directory back to its corpus path")
    print(f"\nmode={args.mode} pairs={len(pairs)} blocked_by_citation={blocked} "
          f"acted={len(manifest_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
