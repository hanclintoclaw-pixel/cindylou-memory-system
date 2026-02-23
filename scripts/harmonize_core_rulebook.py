#!/usr/bin/env python3
"""First-pass OCR harmonization for SR3 Core Rulebook.

Usage:
  python3 scripts/harmonize_core_rulebook.py
  python3 scripts/harmonize_core_rulebook.py --mac-path /path/to/result.txt --deepseek-path /path/to/result.cleaned.md
  python3 scripts/harmonize_core_rulebook.py --output-dir /path/to/output

Notes:
- Input format is expected to use markers like: ===== PAGE 123 =====
- If DeepSeek `result.cleaned.md` is missing, the script can synthesize page-marker text
  from sibling `pages/page_XXXX.md` files for a best-effort first pass.
- Uses Python standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

PAGE_RE = re.compile(r"^=====\s*PAGE\s+(\d+)\s*=====\s*$", re.MULTILINE)
TOKEN_RE = re.compile(r"[a-z0-9]+")

DEFAULT_BASE = Path(
    "/Volumes/carbonite/GDrive/cindylou/Shadowrun_3e_Rules_Library/organized_3e/_ocr_remote"
)
DEFAULT_MAC_PATH = (
    DEFAULT_BASE / "macos_vision/core_rules__SR3_Core_Rulebook_FanPro/result.txt"
)
DEFAULT_DEEPSEEK_PATH = (
    DEFAULT_BASE
    / "deepseek/core_rules__SR3_Core_Rulebook_FanPro/result.cleaned.md"
)
DEFAULT_DEEPSEEK_DIR = (
    DEFAULT_BASE / "deepseek/core_rules__SR3_Core_Rulebook_FanPro"
)
DEFAULT_LOCAL_FALLBACK_OUTPUT = Path("outputs/harmonized_core_firstpass")


@dataclass
class PageMetrics:
    char_count: int
    word_count: int
    line_count: int
    empty: bool
    short: bool
    symbol_noise_ratio: float
    duplicate_line_ratio: float
    quality_score: float
    low_quality: bool
    suspicious: bool


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_pages(marker_text: str) -> Dict[int, str]:
    matches = list(PAGE_RE.finditer(marker_text))
    pages: Dict[int, str] = {}
    for idx, match in enumerate(matches):
        page_no = int(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(marker_text)
        pages[page_no] = marker_text[start:end].strip("\n")
    return pages


def synthesize_markered_text_from_deepseek_pages(deepseek_dir: Path) -> str:
    pages_dir = deepseek_dir / "pages"
    if not pages_dir.exists():
        raise FileNotFoundError(
            f"DeepSeek cleaned file missing and pages dir not found: {pages_dir}"
        )

    page_files = sorted(pages_dir.glob("page_*.md"))
    if not page_files:
        raise FileNotFoundError(f"No page files found in {pages_dir}")

    chunks: List[str] = []
    for pf in page_files:
        stem = pf.stem  # page_0001
        try:
            page_no = int(stem.split("_")[-1])
        except ValueError:
            continue
        text = pf.read_text(encoding="utf-8", errors="replace").strip("\n")
        chunks.append(f"===== PAGE {page_no} =====\n{text}\n")
    if not chunks:
        raise ValueError(f"No parseable DeepSeek page files in {pages_dir}")
    return "\n".join(chunks)


def line_signature(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().lower())


def compute_metrics(text: str) -> PageMetrics:
    stripped = text.strip()
    char_count = len(stripped)
    words = TOKEN_RE.findall(stripped.lower())
    word_count = len(words)
    lines = [ln for ln in (line_signature(ln) for ln in stripped.splitlines()) if ln]
    line_count = len(lines)

    empty = word_count == 0
    short = word_count < 25

    non_space_chars = [c for c in stripped if not c.isspace()]
    symbol_chars = [c for c in non_space_chars if not c.isalnum()]
    symbol_noise_ratio = (len(symbol_chars) / len(non_space_chars)) if non_space_chars else 1.0

    duplicate_line_ratio = 0.0
    if line_count > 1:
        dup_count = line_count - len(set(lines))
        duplicate_line_ratio = dup_count / line_count

    score = 100.0
    if empty:
        score -= 120.0
    if short:
        score -= 30.0
    score -= 60.0 * symbol_noise_ratio
    score -= 40.0 * duplicate_line_ratio
    score += min(word_count, 300) / 20.0  # modest reward for richer text

    low_quality = score < 45.0 or (short and symbol_noise_ratio > 0.28)
    suspicious = empty or word_count < 15 or symbol_noise_ratio > 0.45 or duplicate_line_ratio > 0.45

    return PageMetrics(
        char_count=char_count,
        word_count=word_count,
        line_count=line_count,
        empty=empty,
        short=short,
        symbol_noise_ratio=round(symbol_noise_ratio, 4),
        duplicate_line_ratio=round(duplicate_line_ratio, 4),
        quality_score=round(score, 3),
        low_quality=low_quality,
        suspicious=suspicious,
    )


def token_set(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def jaccard_overlap(a: str, b: str) -> float:
    ta = token_set(a)
    tb = token_set(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def choose_winner(mac_metrics: PageMetrics, deep_metrics: PageMetrics) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if mac_metrics.quality_score > deep_metrics.quality_score:
        winner = "macos"
        reasons.append("higher_quality_score")
    elif deep_metrics.quality_score > mac_metrics.quality_score:
        winner = "deepseek"
        reasons.append("higher_quality_score")
    else:
        # deterministic tie-break toward deepseek cleaned output
        winner = "deepseek"
        reasons.append("tie_break_deepseek")

    if winner == "macos":
        if mac_metrics.short and not deep_metrics.short:
            reasons.append("macos_short_penalty_override")
    else:
        if deep_metrics.short and not mac_metrics.short:
            reasons.append("deepseek_short_penalty_override")

    return winner, reasons


def short_excerpt(text: str, width: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned[:width] + ("..." if len(cleaned) > width else "")


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def page_record(page_no: int, text: str, metrics: PageMetrics) -> Dict[str, object]:
    return {
        "page": page_no,
        "char_count": metrics.char_count,
        "word_count": metrics.word_count,
        "line_count": metrics.line_count,
        "empty": metrics.empty,
        "short": metrics.short,
        "symbol_noise_ratio": metrics.symbol_noise_ratio,
        "duplicate_line_ratio": metrics.duplicate_line_ratio,
        "quality_score": metrics.quality_score,
        "low_quality": metrics.low_quality,
        "suspicious": metrics.suspicious,
        "excerpt": short_excerpt(text, width=200),
    }


def harmonize(mac_pages: Dict[int, str], deep_pages: Dict[int, str]) -> Dict[str, object]:
    all_pages = sorted(set(mac_pages) | set(deep_pages))

    harmonized_chunks: List[str] = []
    meta_pages: List[Dict[str, object]] = []
    review_queue: List[Dict[str, object]] = []

    for p in all_pages:
        mac_text = mac_pages.get(p, "")
        deep_text = deep_pages.get(p, "")

        mac_m = compute_metrics(mac_text)
        deep_m = compute_metrics(deep_text)

        overlap = jaccard_overlap(mac_text, deep_text)
        winner, winner_reasons = choose_winner(mac_m, deep_m)

        chosen_text = mac_text if winner == "macos" else deep_text
        chosen_m = mac_m if winner == "macos" else deep_m

        flags: List[str] = []

        # a) high disagreement
        if overlap < 0.22 and mac_m.word_count >= 20 and deep_m.word_count >= 20:
            flags.append("high_disagreement_low_overlap")

        # b) both low quality
        if mac_m.low_quality and deep_m.low_quality:
            flags.append("both_low_quality")

        # c) chosen still suspicious
        if chosen_m.suspicious:
            flags.append("chosen_suspicious")

        harmonized_chunks.append(f"===== PAGE {p} =====\n{chosen_text.strip()}\n")

        meta_pages.append(
            {
                "page": p,
                "winner": winner,
                "winner_reasons": winner_reasons,
                "overlap_jaccard": round(overlap, 4),
                "flags": flags,
                "sources": {
                    "macos": page_record(p, mac_text, mac_m),
                    "deepseek": page_record(p, deep_text, deep_m),
                },
            }
        )

        if flags:
            review_queue.append(
                {
                    "page": p,
                    "winner": winner,
                    "flags": flags,
                    "overlap_jaccard": round(overlap, 4),
                    "mac_excerpt": short_excerpt(mac_text),
                    "deepseek_excerpt": short_excerpt(deep_text),
                }
            )

    return {
        "harmonized_text": "\n".join(harmonized_chunks).strip() + "\n",
        "meta_pages": meta_pages,
        "review_queue": review_queue,
        "total_pages": len(all_pages),
        "flagged_pages": len(review_queue),
    }


def write_outputs(output_dir: Path, result: Dict[str, object], run_meta: Dict[str, object]) -> Dict[str, Path]:
    ensure_output_dir(output_dir)

    harmonized_md = output_dir / "harmonized.md"
    meta_json = output_dir / "harmonized.meta.json"
    review_md = output_dir / "review_queue.md"
    review_jsonl = output_dir / "review_queue.jsonl"

    harmonized_md.write_text(result["harmonized_text"], encoding="utf-8")

    meta_payload = {
        "run": run_meta,
        "summary": {
            "total_pages": result["total_pages"],
            "flagged_pages": result["flagged_pages"],
        },
        "pages": result["meta_pages"],
    }
    meta_json.write_text(json.dumps(meta_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    review_lines = [
        "# OCR Harmonization Review Queue",
        "",
        f"Total flagged pages: {result['flagged_pages']} / {result['total_pages']}",
        "",
    ]
    for item in result["review_queue"]:
        review_lines.extend(
            [
                f"## Page {item['page']}",
                f"- Winner: `{item['winner']}`",
                f"- Flags: {', '.join(item['flags'])}",
                f"- Overlap (Jaccard): {item['overlap_jaccard']}",
                "- macOS excerpt:",
                "```text",
                item["mac_excerpt"],
                "```",
                "- DeepSeek excerpt:",
                "```text",
                item["deepseek_excerpt"],
                "```",
                "",
            ]
        )
    review_md.write_text("\n".join(review_lines), encoding="utf-8")

    with review_jsonl.open("w", encoding="utf-8") as fh:
        for item in result["review_queue"]:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    return {
        "harmonized_md": harmonized_md,
        "meta_json": meta_json,
        "review_md": review_md,
        "review_jsonl": review_jsonl,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Harmonize OCR pages for SR3 Core Rulebook.")
    parser.add_argument("--mac-path", type=Path, default=DEFAULT_MAC_PATH)
    parser.add_argument("--deepseek-path", type=Path, default=DEFAULT_DEEPSEEK_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DEEPSEEK_DIR / "harmonized_core_firstpass",
    )
    args = parser.parse_args()

    mac_text = load_text(args.mac_path)

    deepseek_input_mode = "result.cleaned.md"
    deep_text = ""
    if args.deepseek_path.exists():
        deep_text = load_text(args.deepseek_path)
    else:
        try:
            deep_text = synthesize_markered_text_from_deepseek_pages(args.deepseek_path.parent)
            deepseek_input_mode = "synthesized_from_pages"
        except FileNotFoundError:
            deepseek_input_mode = "missing_deepseek_fallback_macos_only"
            deep_text = ""

    mac_pages = parse_pages(mac_text)
    deep_pages = parse_pages(deep_text) if deep_text.strip() else {}

    if not mac_pages:
        raise ValueError(f"No PAGE markers found in mac path: {args.mac_path}")

    result = harmonize(mac_pages, deep_pages)

    run_meta = {
        "mac_path": str(args.mac_path),
        "deepseek_path": str(args.deepseek_path),
        "deepseek_input_mode": deepseek_input_mode,
        "output_dir": str(args.output_dir),
    }
    actual_output_dir = args.output_dir
    try:
        paths = write_outputs(actual_output_dir, result, run_meta)
    except PermissionError:
        actual_output_dir = DEFAULT_LOCAL_FALLBACK_OUTPUT
        run_meta["output_dir_fallback"] = str(actual_output_dir)
        paths = write_outputs(actual_output_dir, result, run_meta)

    print(f"WROTE harmonized_md={paths['harmonized_md']}")
    print(f"WROTE meta_json={paths['meta_json']}")
    print(f"WROTE review_md={paths['review_md']}")
    print(f"WROTE review_jsonl={paths['review_jsonl']}")
    print(f"SUMMARY total_pages={result['total_pages']} flagged_pages={result['flagged_pages']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
