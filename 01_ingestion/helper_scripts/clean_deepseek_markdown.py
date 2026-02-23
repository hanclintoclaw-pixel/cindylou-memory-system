#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

TAG_REF_RE = re.compile(r"<\|ref\|>.*?<\|/ref\|>", re.IGNORECASE)
TAG_DET_RE = re.compile(r"<\|det\|>.*?<\|/det\|>", re.IGNORECASE)

COMMON_FIXES = {
    "Shadownrun": "Shadowrun",
    "Shadowrn": "Shadowrun",
    "Edltion": "Edition",
    "THlRD": "THIRD",
    "FASA Corporatlon": "FASA Corporation",
}


def strip_tags(text: str) -> str:
    text = TAG_REF_RE.sub("", text)
    text = TAG_DET_RE.sub("", text)
    return text


def apply_common_fixes(text: str) -> str:
    for bad, good in COMMON_FIXES.items():
        text = text.replace(bad, good)
    return text


def remove_page_number_lines(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        s = line.strip()
        if re.fullmatch(r"\d{1,4}", s):
            continue
        if re.fullmatch(r"page\s+\d{1,4}", s, flags=re.IGNORECASE):
            continue
        out.append(line)
    return out


def dedupe_consecutive_lines(lines: list[str]) -> list[str]:
    out = []
    prev = None
    for line in lines:
        s = line.strip()
        if s and prev == s:
            continue
        out.append(line)
        if s:
            prev = s
    return out


def dehyphenate(text: str) -> str:
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def join_wrapped_lines(lines: list[str]) -> list[str]:
    out = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            c = cur.rstrip()
            n = nxt.lstrip()
            if c and n and c[-1] not in ".:;!?" and not c.endswith("  ") and n[:1].islower():
                out.append(c + " " + n)
                i += 2
                continue
        out.append(cur)
        i += 1
    return out


def normalize_headings(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            out.append("")
            continue
        if len(s) < 70 and s.upper() == s and any(ch.isalpha() for ch in s):
            out.append(f"## {s.title()}")
        else:
            out.append(line)
    return out


def clean_text(text: str) -> str:
    text = strip_tags(text)
    text = apply_common_fixes(text)
    text = dehyphenate(text)
    lines = text.splitlines()
    lines = remove_page_number_lines(lines)
    lines = dedupe_consecutive_lines(lines)
    lines = join_wrapped_lines(lines)
    lines = normalize_headings(lines)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()

    raw = args.input.read_text(encoding="utf-8", errors="replace")
    cleaned = clean_text(raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(cleaned, encoding="utf-8")


if __name__ == "__main__":
    main()
