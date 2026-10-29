#!/usr/bin/env python3
"""Deterministic, reversible OCR repair for the SR3 rules corpus.

Born from the 2026-10-28 audit, which separated defects a script can settle from
defects that need the printed book. The dividing line is provability: a fix ships
here only when the corpus itself proves the intended text, so no reading of the PDF
is required and no game mechanic can change under a wrong guess.

Fixed (deterministic, self-proving):
  c1-control      C1 control characters left by a cp1252 misread. U+0095 is a bullet
                  and U+0099 a trademark in cp1252, and the corpus shows them sitting
                  exactly where a bullet separator belongs ("Type: P \x95 Action: ...").
  dice-dg         "<n>DG" is "<n>D6". Proved inside the corpus, not from the book:
                  SR3_Matrix_7909:10479 reads "roll 1DG or 2D6", and Core 26907 reads
                  "1DG (Astral)/F + 9 + 1D6 (Physical)" - the same quantity spelled two
                  ways in one line, one of them wrong. The digit anchor is load-bearing:
                  bare "DG" occurs twice as legitimate text (a person's initials).

Deliberately NOT fixed here, reported for human review against the PDF instead:
  table column bleed (firearms/melee rows detached from labels), truncated INIT lines,
  empty/failed page bodies, and "Target Number Z". TN-Z is usually 2 but is genuinely
  contextual, and silently inventing a target number at the table is worse than a gap.

Every rewrite is preceded by a whole-file backup under the data tier, and a row is
appended to a JSONL change log so any single edit can be reverted by hand.

Usage:
  ocr_repair.py audit                 # count what would change, write nothing
  ocr_repair.py apply                 # back up, rewrite, log
  ocr_repair.py report                # print the human-review backlog
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path("/Volumes/carbonite/claw/data/cindylou/cleaned/memory/00_sources/rules_references")
# Intermediates/caches are the sanctioned tier for rebuildable data artifacts.
STAGING = Path("/Volumes/carbonite/claw/data/cindylou/intermediates/ocr-repair")

# cp1252 C1 codepoints that survive a Latin-1-style misread as invisible control chars.
C1_MAP = {
    "\u0095": "\u2022",  # bullet
    "\u0099": "\u2122",  # trademark
    "\u0092": "\u2019",  # right single quote
    "\u0093": "\u201c",  # left double quote
    "\u0094": "\u201d",  # right double quote
    "\u0096": "\u2013",  # en dash
    "\u0097": "\u2014",  # em dash
    "\u0098": "\u2018",  # left single quote
}

# Digit-anchored so legitimate "DG" prose is untouched.
DICE_DG = re.compile(r"(?<=\d)DG\b")

# Human-review backlog detectors. Count only; never rewrite.
BACKLOG = {
    "table-column-bleed": re.compile(r"^\s*(?:\d+(?:\s*[+\-/]\s*\d+)?|[A-Z]{1,3})\s*$"),
    "target-number-z": re.compile(r"Target Number\s+Z\b", re.I),
    "truncated-init": re.compile(r"INIT:?\s*[^\n]*\+\s*\d+\s*D(?![6G8])\s*$", re.I),
    "corrupt-damage-code": re.compile(r"\bn\s*[OLMDS]\b"),
}


def sources() -> list[Path]:
    return sorted(p for p in CORPUS.rglob("source.md") if p.is_file())


def counts_for(text: str) -> Counter:
    c: Counter = Counter()
    for ch in text:
        if ch in C1_MAP:
            c["c1-control"] += 1
    c["dice-dg"] += len(DICE_DG.findall(text))
    for name, pat in BACKLOG.items():
        c[name] += len(pat.findall(text))
    return c


def repair(text: str) -> tuple[str, Counter]:
    """Apply only the provable substitutions. Returns new text and per-class counts."""
    applied: Counter = Counter()
    out = text
    for src, dst in C1_MAP.items():
        n = out.count(src)
        if n:
            out = out.replace(src, dst)
            applied["c1-control"] += n
    out, n = DICE_DG.subn("D6", out)
    if n:
        applied["dice-dg"] += n
    return out, applied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["audit", "apply", "report"])
    args = ap.parse_args()

    if not CORPUS.is_dir():
        print(f"corpus missing: {CORPUS}", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.mode == "apply":
        (STAGING / stamp / "backup").mkdir(parents=True, exist_ok=True)

    totals: Counter = Counter()
    touched: list[Path] = []
    log_rows: list[dict] = []

    for path in sources():
        try:
            original = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"read failed {path}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        pre = counts_for(original)
        totals.update(pre)
        if args.mode == "apply":
            fixed, applied = repair(original)
            if applied:
                backup = STAGING / stamp / "backup" / path.relative_to(CORPUS.parent)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
                path.write_text(fixed, encoding="utf-8")
                touched.append(path)
                for cls, n in applied.items():
                    log_rows.append(
                        {
                            "at": datetime.now(timezone.utc).isoformat(),
                            "file": str(path),
                            "class": cls,
                            "count": n,
                            "backup": str(backup),
                        }
                    )

    if args.mode == "report":
        print("Human-review backlog (scripted fixes deliberately declined):")
        for name in BACKLOG:
            print(f"  {name:22s} {totals[name]:>6d}")
        print("\nWhy these stay manual: each needs the printed page to resolve, and a")
        print("wrong number voiced at the table costs more than saying 'check the table'.")
        return 0

    label = "would change" if args.mode == "audit" else "changed"
    print(f"{args.mode.upper()} over {len(sources())} files")
    print(f"  scriptable  c1-control={totals['c1-control']} dice-dg={totals['dice-dg']}  ({label})")
    print(f"  manual      " + " ".join(f"{k}={totals[k]}" for k in BACKLOG if totals[k]))
    if args.mode == "apply":
        print(f"  files rewritten: {len(touched)}")
        for p in touched:
            print(f"    {p.relative_to(CORPUS)}")
        if log_rows:
            (STAGING / stamp / "changes.jsonl").write_text(
                "\n".join(json.dumps(r) for r in log_rows) + "\n", encoding="utf-8"
            )
            print(f"  log/backups: {STAGING / stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
