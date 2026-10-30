#!/usr/bin/env python3
"""Precision harness for page-level SR3 rules retrieval.

Why this exists instead of more score tuning. Three consecutive attempts to make the
ruling-shape signal a score BOOSTER each promoted a fluent wrong page: an archetype stat
block, then "Edged Weapons (Strength) governs the use of hand-held melee weapons" as the
answer to a stealth question, then "OCT field agents are quickly passed on to their
back-up" for a range question (because "quickly" contains "quick" and the range pattern
matched a substring). Anything that multiplies a score gets gamed by whichever page has
the most matching text. So ranking reports a signal and a separate gate decides whether
the table hears it. This harness measures that gate.

What counts as passing. Only strings grepped out of the corpus itself are expected here.
An expectation written from memory of the rulebook is exactly the uncited-stat failure
this corpus exists to prevent, so every EXPECTS below was read off the cleaned text
first, and the string is verified present in the corpus before the case is trusted.

Usage:
    python3 scripts/rules_eval.py            # report
    python3 scripts/rules_eval.py --strict   # nonzero exit if precision < 1.0
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "memory_bridge", REPO / "05_serving" / "memory_bridge.py"
)
mb = importlib.util.module_from_spec(_spec)
sys.modules["memory_bridge"] = mb
_spec.loader.exec_module(mb)

EXCLUDE = mb.RULES_EXCLUDED_SEGMENTS
# Mirrors the bridge default so the harness measures the thing that will actually run.
# Overridable from the shell because the corroboration requirement is the main knob: it
# buys precision with recall, and the trade should be measured rather than asserted.
MIN_RESPONSIVE_BOOKS = int(os.environ.get("RULES_MIN_BOOKS", "2"))
# When set to a comma-separated list, only pages whose ruling shape is in the list may be
# accepted, and a page with no shape at all is declined. Used to test whether restricting
# to the high-precision printed forms (attribute links, damage codes, range bands, drain
# codes) is enough to make proactive injection safe to enable. Empty = all shapes allowed.
_SHAPE_ALLOW_RAW = os.environ.get("RULES_SHAPE_ALLOW", "").strip()
SHAPE_ALLOWLIST: tuple[str, ...] | None = (
    tuple(t.strip() for t in _SHAPE_ALLOW_RAW.split(",") if t.strip())
    if _SHAPE_ALLOW_RAW
    else None
)
# --legacy scores the pre-change path (whole-book keyword_search, first snippet wins) so
# the improvement claim has a measured baseline instead of a narrative.
LEGACY = "--legacy" in sys.argv

# (question, terms that must appear in the accepted excerpt, corpus-verified proof string)
# proof is grepped against the whole corpus at startup: if a proof string is absent, the
# case is skipped rather than counted as a failure, so the suite cannot fail because
# someone legitimately repaired a page.
CASES = [
    (
        "what attribute is stealth linked to",
        ("Stealth (Quickness)",),
        "Stealth (Quickness)",
    ),
    (
        "what attribute governs stealth tests",
        ("Stealth (Quickness)",),
        "Stealth (Quickness)",
    ),
    (
        "what is the damage code of an ares predator",
        ("9M",),
        "9M",
    ),
    (
        "how many dice do I roll for a drain resistance test",
        ("Drain Resistance Test",),
        "Drain Resistance Test",
    ),
    (
        "what is short range for a pistol in meters",
        ("short range",),
        "5-meter short range",
    ),
    (
        "how does initiative work in combat",
        ("Initiative",),
        "Initiative",
    ),
    (
        "what is the target number for a complex action",
        ("Complex Action",),
        "Complex Action",
    ),
    # Strings below were grepped from the corpus before being used as expectations, so each
    # is a real ruling these 54 books carry, not a recollection of the rulebook.
    (
        "what is the rule of one",
        ("Rule of One",),
        "Rule of One",
    ),
    (
        "what happens when I roll a glitch",
        ("Glitch",),
        "Glitch",
    ),
    (
        "how do I dodge an attack",
        ("Dodge Test",),
        "Dodge Test",
    ),
    (
        "how does astral perception work",
        ("Astral Perception",),
        "Astral Perception",
    ),
    (
        "what is recoil compensation on a firearm",
        ("Recoil Compensation",),
        "Recoil Compensation",
    ),
    (
        "how does astral combat work",
        ("Astral Combat Test",),
        "Astral Combat Test",
    ),
]

# Must NOT be answered from the rules corpus. Each is either not a rules question, or a
# rules question whose answer genuinely is not in these 54 books. Speaking either one is
# the failure that costs the table more than a shrug.
DECLINE_CASES = [
    # Absent from the corpus per the sr3-rules-corpus-lookup skill: a brand name with no
    # entry anywhere. Mapping it to the nearest row is a vendor guess, not a ruling.
    "what is the damage on a sandevistan",
    # Not rules at all - the equipment tier owns this, and the rules tier must not compete.
    "what does an Ares Predator cost",
    # Table talk mentioning rules vocabulary.
    "I was thinking about rolling initiative later",
    # A campaign fact, not a rules fact.
    "who leads the Princeps Group",
    # Real SR3 vocabulary that these 54 books do not carry (grepped: zero hits in
    # core_rules + sourcebooks). These are the important decline cases: a fluent
    # approximation of a rule the corpus genuinely lacks is the exact failure mode the
    # rules-honesty instruction was written to stop. Declining here is the win condition.
    "how many dice for a countermagic test",
    "what is the wound penalty modifier",
    "how do extended tests work",
    "how many dice for a soak test",
]


def corpus_contains(needle: str) -> bool:
    for doc, _mk, body, _book, _sec in mb._page_units("sr3_rules"):
        if needle in body:
            return True
    return False


def _near(text: str, needle: str, subject: str, window: int = 180) -> bool:
    """Is the ruling stated ABOUT the thing asked about?

    A plain substring test over a 900-char page window is too weak to report, and an earlier
    run of this harness proved it: the stealth case "passed" while its preview read "skill
    covers all forms of underwater diving... (B/K) Default: Bo" - the Aquatics skill page -
    only because 'Stealth (Quickness)' happened to fall inside the same 900 chars. Injecting
    that would have the model read a paragraph about swimming and derive a stealth link from
    it. Requiring the subject within `window` characters of the ruling is the excerpt-level
    form of the corpus skill's rule that a chunk must answer the question asked, not merely
    come from the right book.
    """
    low = text.lower()
    n = needle.lower()
    if not subject:
        return n in low
    for m in re.finditer(re.escape(n), low):
        lo = max(0, m.start() - window)
        hi = min(len(low), m.end() + window)
        if re.search(r"(?<![a-z0-9])" + re.escape(subject.lower()) + r"(?![a-z0-9])", low[lo:hi]):
            return True
    return False


def run_case_legacy(q: str, expects: tuple[str, ...]) -> dict:
    """The behaviour before page-level retrieval: rank whole books, inject the top snippet.

    This is what the disabled tier actually did - keyword_search over 54 whole-book
    documents, first hit's 220-character window injected into the prompt. Measuring it on
    the same cases is the only way to say whether the structural change helped.
    """
    hits = mb.keyword_search(query=q, scope="sr3_rules", limit=6)
    hits = [
        h
        for h in hits
        if not any(seg in h.doc_id.lower() for seg in EXCLUDE)
    ]
    if not hits:
        return {"q": q, "accepted": False, "precise": False, "missing": list(expects),
                "reason": "no_pages", "top": None, "responsive_books": [], "preview": ""}
    top = hits[0]
    missing = [e for e in expects if not _near(top.snippet, e, "")]
    book = top.filename
    return {
        "q": q,
        "accepted": True,
        "precise": not missing,
        "missing": missing,
        "reason": "legacy_top_book",
        "top": {
            "book": book[:34],
            "citation": top.doc_id[-42:],
            "score": top.score,
            "shape": "-",
            "hits": 0,
            "excerpt_source": "legacy",
            "chars": len(top.snippet),
        },
        "responsive_books": [],
        "preview": top.snippet[:150],
    }


def run_case(q: str, expects: tuple[str, ...]) -> dict:
    if LEGACY:
        return run_case_legacy(q, expects)
    a = mb.page_answer(
        query=q, min_responsive_books=MIN_RESPONSIVE_BOOKS, shape_allowlist=SHAPE_ALLOWLIST
    )
    if not a.hits:
        return {"q": q, "accepted": False, "why": "no pages", "top": None}
    top = a.hits[0]
    missing = [e for e in expects if not _near(top.snippet, e, top.subject)]
    # Accepted means the gate said speak; precise means what it would speak is the ruling.
    return {
        "q": q,
        "accepted": a.accepted,
        "precise": not missing,
        "missing": missing,
        "reason": a.reason,
        "top": {
            "book": top.book,
            "citation": top.citation(),
            "score": top.score,
            "shape": top.ruling_shape,
            "hits": top.ruling_hits,
            "excerpt_source": top.excerpt_source,
            "chars": len(top.snippet),
        },
        "responsive_books": a.responsive_books,
        "preview": top.snippet[:150],
    }


def main() -> int:
    strict = "--strict" in sys.argv
    print("== proof strings present in corpus? ==")
    live = []
    for q, expects, proof in CASES:
        ok = corpus_contains(proof)
        print(f"  {'ok  ' if ok else 'SKIP'} {proof!r}")
        if ok:
            live.append((q, expects))

    print("\n== accept cases: is the ruling in the EXCERPT that would be spoken? ==")
    accepted_precise = accepted_wrong = declined = 0
    for q, expects in live:
        r = run_case(q, expects)
        t = r["top"] or {}
        if not r["accepted"]:
            declined += 1
            status = "DECLINE"
        elif r["precise"]:
            accepted_precise += 1
            status = "PASS"
        else:
            accepted_wrong += 1
            status = "WRONG"
        print(f"\n[{status}] {q}")
        if t:
            print(
                f"    {t['book'][:34]:<34} {t['citation'][:42]:<42} "
                f"score={t['score']:<8} shape={t['shape'] or '-':<14} "
                f"hits={t['hits']} anchor={t['excerpt_source']} reason={r['reason']}"
            )
            print(f"    missing={r.get('missing')} responsive_books={len(r['responsive_books'])}")
            print(f"    {r['preview']}")

    print("\n== decline cases: does the gate stay shut? ==")
    # A leaked decline case is also a wrong thing spoken. Counting precision only over the
    # accept set flatters the gate: the decline set exists precisely to find wrong accepts
    # on questions the corpus cannot answer, and those are the most damaging ones at the
    # table (a fluent approximation of a rule the books never stated). Combined precision
    # below is the number that should gate deployment.
    accept_spoken = accept_right = 0
    dpass = dfail = 0
    for q in DECLINE_CASES:
        if LEGACY:
            hs = mb.keyword_search(query=q, scope="sr3_rules", limit=3)
            hs = [h for h in hs if not any(seg in h.doc_id.lower() for seg in EXCLUDE)]
            leak = bool(hs)
            if leak:
                dfail += 1
                print(f"[LEAK] {q} -> {hs[0].filename} score={hs[0].score}")
                print(f"       {hs[0].snippet[:120]}")
            else:
                dpass += 1
                print(f"[SHUT] {q}")
            continue
        a = mb.page_answer(
            query=q, min_responsive_books=MIN_RESPONSIVE_BOOKS, shape_allowlist=SHAPE_ALLOWLIST
        )
        if a.accepted:
            dfail += 1
            accept_spoken += 1
            print(f"[LEAK] {q} -> {a.hits[0].book} {a.hits[0].citation()} shape={a.hits[0].ruling_shape}")
            print(f"       {a.hits[0].snippet[:120]}")
        else:
            dpass += 1
            print(f"[SHUT] {q} (reason={a.reason}, books={a.responsive_books[:2]})")

    total = accepted_precise + accepted_wrong + declined
    n = len(live)
    mode = "LEGACY whole-book" if LEGACY else f"page-level min_books={MIN_RESPONSIVE_BOOKS}"
    print(f"\n[{mode}] of {n} accept cases: {accepted_precise} precise, "
          f"{accepted_wrong} WRONG, {declined} declined")
    print(f"recall: {accepted_precise}/{n} ({accepted_precise / max(1, n):.0%})")
    spoken = accepted_precise + accepted_wrong + dfail
    right = accepted_precise
    prec = right / max(1, spoken)
    print(f"\nCOMBINED precision when speaking: {right}/{spoken} ({prec:.0%})"
          f"  <-- the only number that should gate deployment")
    print(f"  (accept set: {accepted_precise} right / {accepted_wrong} wrong;"
          f" decline set leaks: {dfail})")
    print(f"decline cases: {dpass}/{dpass + dfail} shut")
    return 1 if strict and (prec < 1.0 or dfail) else 0


if __name__ == "__main__":
    raise SystemExit(main())
