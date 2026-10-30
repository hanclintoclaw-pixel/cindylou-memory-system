#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from config.pipeline_paths import get_paths

P = get_paths()
REPO_ROOT = Path(P.repo_root)
CODE_ROOT = Path(P.code_root)
MEMORY_ROOT = Path(P.memory_root)
AUDIT_DIR = P.data_root / "logs"
AUDIT_FILE = AUDIT_DIR / "memory_upserts.jsonl"
FACTS_FILE = MEMORY_ROOT / "99_runtime" / "chat_facts.jsonl"
WORKSPACE_ROOT = Path(
    os.environ.get(
        "CINDY_WORKSPACE_ROOT",
        str(Path.home() / ".openclaw" / "workspace-cindylou"),
    )
)
CAMPAIGN_WIKI_ROOT = Path(
    os.environ.get(
        "CAMPAIGN_WIKI_ROOT",
        str(CODE_ROOT / "campaign-wiki"),
    )
)
SCAN_MOUNTED_CAMPAIGN = (
    os.environ.get("MEMORY_SCAN_MOUNTED_CAMPAIGN", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
DATE_NOTE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\.md$")

# Returned doc_ids are resolvable by get_doc: relative to MEMORY_ROOT by default,
# namespaced for the other search roots. Kept disjoint because the wiki and the
# workspace each contain a "memory" directory, so bare relative paths would collide.
WIKI_PREFIX = "wiki/"
WORKSPACE_PREFIX = "workspace/"


@dataclass
class SearchHit:
    doc_id: str
    filename: str
    score: float
    snippet: str
    edition_tag: str = "SR3"
    page: str | None = None


def _iter_docs(scope: str = "all") -> Iterable[Path]:
    if not MEMORY_ROOT.exists():
        memory_root_exists = False
    else:
        memory_root_exists = True
    roots: list[Path] = []
    s = (scope or "all").lower()
    if s in {"all", "campaign"}:
        roots.extend(_campaign_search_roots())
    if s in {"all", "sr3", "sr3_rules", "rules", "lore"}:
        if memory_root_exists:
            roots.append(MEMORY_ROOT / "lore")
            roots.append(MEMORY_ROOT / "topics")
            roots.append(MEMORY_ROOT / "00_sources" / "rules_references")
    if memory_root_exists and s != "campaign":
        roots.append(MEMORY_ROOT / "90_derived")

    seen = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".md":
            paths = [root]
        elif root == WORKSPACE_ROOT / "memory":
            paths = (
                p for p in root.rglob("*.md")
                if DATE_NOTE_RE.fullmatch(p.name)
            )
        else:
            paths = root.rglob("*.md")
        for p in paths:
            rp = str(p.resolve())
            if rp in seen:
                continue
            seen.add(rp)
            yield p


def _campaign_search_roots() -> list[Path]:
    roots: list[Path] = []
    dossier = WORKSPACE_ROOT / "PARTY_DOSSIER.md"
    workspace_memory = WORKSPACE_ROOT / "memory"
    if dossier.exists():
        roots.append(dossier)
    if CAMPAIGN_WIKI_ROOT.exists():
        roots.append(CAMPAIGN_WIKI_ROOT)
    if workspace_memory.exists():
        roots.append(workspace_memory)
    mounted_campaign = MEMORY_ROOT / "campaign"
    if SCAN_MOUNTED_CAMPAIGN and mounted_campaign.exists():
        roots.append(mounted_campaign)
    return roots


def _doc_id(p: Path) -> str:
    for root, prefix in (
        (MEMORY_ROOT, ""),
        (CAMPAIGN_WIKI_ROOT, WIKI_PREFIX),
        (WORKSPACE_ROOT, WORKSPACE_PREFIX),
    ):
        try:
            return prefix + p.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            continue
    return p.name


def _snippet(text: str, idx: int, span: int = 220) -> str:
    if idx < 0:
        return text[:span].replace("\n", " ").strip()
    start = max(0, idx - span // 3)
    end = min(len(text), idx + span)
    return text[start:end].replace("\n", " ").strip()


_WORD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _term_count(low_text: str, term: str) -> int:
    """Whole-word occurrences only.

    Plain str.count() matched substrings, so a query for "Tom Erlichman" scored 331
    hits against the 768 KB Rigger 3 OCR blob purely on "tom" inside AUTOMOBILE /
    KINGDOM / BOTTOM, burying the actual NPCs/Tom-Erlichman.md page.
    Lookarounds rather than \\b so terms with punctuation on either end still match.
    """
    pat = _WORD_RE_CACHE.get(term)
    if pat is None:
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")
        _WORD_RE_CACHE[term] = pat
    return len(pat.findall(low_text))


def keyword_search(query: str, scope: str = "all", limit: int = 8) -> list[SearchHit]:
    q = (query or "").strip()
    if not q:
        return []

    terms = [t for t in re.split(r"\s+", q.lower()) if t]
    candidates: list[tuple[Path, str, list[int], int]] = []

    for doc in _iter_docs(scope):
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        low = text.lower()
        counts = [_term_count(low, t) for t in terms]
        if not any(counts):
            continue
        candidates.append((doc, text, counts, low.find(terms[0])))

    if not candidates:
        return []

    # Smooth IDF over the candidate set. log((1+N)/(1+df)) goes to 0 for a term that
    # appears in every document, so filler such as "who"/"is"/"the" drops out; a
    # distinctive surname such as "erlichman" carries the ranking.
    n_docs = len(candidates)
    idf = [
        math.log((1.0 + n_docs) / (1.0 + sum(1 for _, _, c, _ in candidates if c[i] > 0)))
        for i in range(len(terms))
    ]

    hits: list[SearchHit] = []
    for doc, text, counts, first_idx in candidates:
        # Saturating tf: without this a 1.4 MB rulebook with 1500 incidental mentions
        # of a filler word outranks a 12 KB NPC page that is about the thing asked.
        tf = [1.0 + math.log(c) if c > 0 else 0.0 for c in counts]
        # Length normalisation: a multi-megabyte OCR dump must not outrank a short
        # page on raw term frequency alone.
        norm = 1.0 + math.log10(max(1.0, len(text) / 4000.0))
        score = sum(t * w for t, w in zip(tf, idf)) / norm
        # Filename is a strong intent signal (NPC / host / topic pages are named
        # after the thing being asked about).
        stem = re.sub(r"[^a-z0-9]+", " ", doc.stem.lower())
        score += sum(w * 3.0 for t, w in zip(terms, idf) if t in stem)
        # Anchor the excerpt on the most discriminative term that is actually present,
        # not on terms[0]. first_idx used to be low.find(terms[0]) - the position of the
        # first word the asker happened to type. "how much damage does a pistol do" is
        # therefore anchored at the first "how" in each book: char 6,875 of the Handbook,
        # inside the credits block, which is why that query returned "Matrix from original
        # miteral by Paul Humel Diane Piron-Gelman" for a pistol damage question. Reordering
        # the same query to "pistol damage how much does a do" moves the excerpt to a
        # different part of the same document at an identical score - proof that word order,
        # not relevance, was choosing what the table got shown.
        #
        # It also closes the real front-matter leak. When terms[0] is absent from a document
        # str.find returns -1 and _snippet falls back to text[:220], i.e. the literal opening
        # of the file - which in the OCR corpus is the mangled cover page ("O HADOWRUN
        # T• H • İ • R • D"). That is how cover-page noise reached answers: not ranking, just
        # an unanchored excerpt. Stripping front matter from the corpus leaves this path
        # broken, so it had to be fixed here rather than upstream.
        #
        # Anchor choice cannot move a document up or down the list - it never touches score -
        # so this changes only which 220 characters are shown. Highest IDF, then longest,
        # then most frequent: "pistol" beats "damage" beats "how".
        present = [(idf[i], len(t), counts[i], i) for i, t in enumerate(terms) if counts[i] > 0]
        if present:
            anchor_idx = text.lower().find(terms[max(present)[3]])
        else:
            anchor_idx = first_idx
        hits.append(
            SearchHit(
                doc_id=_doc_id(doc),
                filename=doc.name,
                score=float(round(score, 3)),
                snippet=_snippet(text, anchor_idx),
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: max(1, min(limit, 30))]


def semantic_search(query: str, scope: str = "all", limit: int = 8) -> list[SearchHit]:
    # Fallback semantic mode: keyword retrieval until embedding index endpoint is wired.
    return keyword_search(query=query, scope=scope, limit=limit)


# ---------------------------------------------------------------------------
# Page-level retrieval for the SR3 rules corpus
# ---------------------------------------------------------------------------
#
# Why this exists as its own function rather than a flag on keyword_search.
#
# keyword_search scores a whole book as one document. In this corpus a document is
# up to 1.4 MB / 350 pages, so the score can only ever answer WHICH BOOK is relevant;
# the passage shown is then chosen by an anchoring heuristic inside _snippet. That is
# the structural reason the rules tier could not be trusted into the live wake path:
#
#   * "what is the range band for short range pistol" - the ruling sits at line 9,728
#     of core_rules/SR3_Core_Rulebook_FanPro/source.md, inside a 1.4 MB document. The
#     book was retrieved; the ruling never was, because 220 characters around an anchor
#     cannot reach it and the score has no way to prefer the page that holds it.
#   * Two books can "corroborate" each other while agreeing on nothing, because both
#     matched somewhere in 350 pages of boilerplate. Agreement computed over whole
#     books is not evidence.
#   * IDF is computed over books, so "pistol" carries the same weight whether it is the
#     subject of a weapons table or one word in a contents page.
#
# The corpus already carries the segmentation the fix needs - the OCR pass wrote
# ===== PAGE n ===== markers (3,864 of them across 54 books). So the unit becomes the
# printed page, IDF is computed over pages, and the excerpt is a whole page rather
# than a heuristic window. Measured cold, splitting every page costs 0.474s for the
# whole corpus, which fits the wake path's 4.5s budget without an index; there is no
# chunker or embedding store to keep in sync (see semantic_search above).

PAGE_MARKER_RE = re.compile(r"===== PAGE (\d+) =====")

# Measured in scripts/rules_eval.py, not decided by taste. See page_answer's docstring.
RULES_REQUIRE_SHAPE = (
    os.environ.get("RULES_REQUIRE_SHAPE", "0").strip().lower() in {"1", "true", "yes", "on"}
)

# Printed folios, read out of the page's own text rather than inferred from the marker.
# The skill's rule is that OCR markers run ahead of the printed footer (they run +2 in
# the core rulebook, measured across all 284 legible footers), so quoting a marker as a
# page number is a guess. When a page carries its own footer we cite that; when it does
# not, we say the printed page is not legible rather than silently subtracting 2.
_FOOTER_RES = (
    re.compile(r"^\s*(\d{1,3})\s*Shadowrun,?\s*Third\s+Edition", re.MULTILINE),
    re.compile(r"Shadowrun,?\s*Third\s+Edition\s*(\d{1,3})"),
)

# Pages this small are column fragments, drop caps, or blank versos. They can score high
# on a saturated tf because a single mention in 80 characters is a perfect density.
_MIN_PAGE_CHARS = 120

# Function words and asker's own verbs. "governs", "means", "do", "does" are rare in this
# corpus (they are the asker's phrasing, not the book's), so a rarity-based ranking of
# query terms puts them at the top and then uses them as a veto. Measured: with
# "what attribute governs stealth tests", the rarest term was "governs", which occurs only
# on the Negotiation page ("The Negotiation Skill governs any interaction..."). The correct
# page - marker 89 of the Core Rulebook, which prints 'Stealth (Quickness)' - was filtered
# out for not containing it. Rarity is a good tiebreaker and a terrible gate.
_STOP_TERMS = frozenset(
    """
    a an the and or but if then than that this these those there here what which who whom
    whose when where why how is are was were be been being do does did doing have has had
    having would should could can may might must will shall need wants want use uses used
    using make makes made take takes got get gets give gives tell tells mean means meaning
    i me my we our you your they them their he she it its his her
    for from into onto about above under between during while with without of in on at to
    also just like same other different such very really quite please okay ok hey hi
    cindy cindylou cindyloubot cindey sindy bot
    """.split()
)

# A candidate page must carry real topical overlap, not one lucky word.
_MIN_TERMS_PRESENT = 2


def _query_terms(query: str) -> list[str]:
    """Split a query into content terms, keeping order and dropping function words.

    Falls back to the raw tokens when everything filtered away, so a one-word question
    still retrieves rather than silently returning nothing.
    """
    toks = [t for t in re.split(r"\s+", (query or "").lower()) if len(t) > 1]
    kept = [t for t in toks if t not in _STOP_TERMS]
    return kept or toks


# --- ruling shapes -----------------------------------------------------------
#
# Coverage and density cannot settle the stealth case, and the instrumented scorer
# proved it: the correct page (Core Rulebook marker 89, Handbook marker 87) has full
# term coverage and ties the winner on density, losing only to length normalisation
# against a 3,436-char Quick Start archetype page. No stopword list fixes that, because
# "governs" is genuine book vocabulary - the rulebook writes "the Negotiation Skill
# governs any interaction". Two pages can share every query term and only one state a
# ruling.
#
# What separates them is printed form. SR3 states a skill link as `Skill (Attribute)`,
# a damage value as a damage code, a pool as Nd6. Those are shapes, not keywords, and
# they are corpus-evidenced: the same books print `Negotiation (Charisma)`,
# `Stealth (Quickness)`, `Car (Reaction)`, `Damage Code of 9M`, `Drain +1(M)`.
# A page that puts the asked-about subject next to the asked-about shape is stating the
# ruling; a page that merely discusses both words is not. This is the retrieval form of
# the corpus skill's rule that agreement means nothing until the chunk is confirmed
# responsive - "the chunk must answer the question asked, not name the book that might".

_SR3_ATTRIBUTES = (
    "strength", "body", "quickness", "reaction", "charisma", "intelligence",
    "willpower", "essence", "magic", "sanity", "edge",
)

# (family name, matcher over page text, query terms that select the family)
_RULE_SHAPES: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    ("attribute_link",
     re.compile(r"\(\s*(?:" + "|".join(_SR3_ATTRIBUTES) + r")\s*\)", re.I),
     ("attribute", "skill", "linked", "link", "connected", "governs", "governed", "quickness")),
    ("damage_code",
     re.compile(r"\b(?:damage code\b[^.;\n]{0,24}|\b\d{1,2}\s*[SMD]\b)", re.I),
     ("damage", "damage code", "soak", "stun", "man", "knockout")),
    ("dice_pool",
     re.compile(r"\b\d+[dD]\d+\b|\bdice pool\b", re.I),
     ("dice", "pool", "dice pool", "how many dice")),
    ("target_number",
     re.compile(r"\btarget number\b|\bTN\b", re.I),
     ("target", "target number", "tn", "difficulty", "modifier")),
    ("drain_code",
     re.compile(r"\+\d+\s*\(\s*[SDM]\s*\)", re.I),
     ("drain", "drain code", "backlash")),
    ("range_band",
     re.compile(r"\b(?:short|medium|long|extreme) range\b|\b\d+\s*-\s*\d+\s*meters?\b", re.I),
     ("range", "range band", "short range", "meters", "distance")),
)

# How close the subject term must sit to the shape for it to count as a ruling about
# that subject. Deliberately tight: "stealth" three thousand characters from an
# unrelated `(Charisma)` is not a ruling about stealth.
_RULING_ADJACENCY = 60


def _rule_families(terms: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    picked: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()
    for name, pat, cues in _RULE_SHAPES:
        if name in seen:
            continue
        if any(c in terms for c in cues):
            picked.append((name, pat))
            seen.add(name)
    return picked


# Cue vocabulary for a family cannot double as evidence of what the page is about.
# First measured attempt counted every long query term as the subject, so for
# "what attribute governs stealth tests" the subject set included "governs" - which is
# itself an attribute_link cue. The Core Rulebook's skill pages all read
# "Edged Weapons (Strength) Edged Weapons governs the use of...", so (Strength) sat next
# to "governs" and those pages took the boost and finished 1st and 2nd, while the page
# actually printing `Stealth (Quickness)` stayed at 6th. Had that been injected, the table
# would have heard "Edged Weapons (Strength)" as the answer to a stealth question: wrong,
# fluent, and cited. The subject must be the thing ASKED ABOUT, never the phrasing that
# selected the shape.


def _ruling_shape(
    body: str, terms: list[str], families
) -> tuple[str, int]:
    """Return (family, hits) for shapes printed next to the asked-about subject.

    Each family scores against its own subject set: content terms with that family's cue
    words removed. "stealth" can make an attribute_link count; "governs" cannot, because
    "governs" is what makes it an attribute_link in the first place.
    """
    if not families:
        return "", 0
    low = body.lower()
    best_family, best_hits = "", 0
    for name, pat in families:
        cues = next(
            (c for nm, _p, c in _RULE_SHAPES if nm == name), ()
        )
        subs = [
            t for t in terms
            if len(t) >= 4 and t not in cues and t not in _STOP_TERMS
        ]
        if not subs:
            continue
        hits = 0
        for m in pat.finditer(body):
            lo = max(0, m.start() - _RULING_ADJACENCY)
            window = low[lo:m.end() + _RULING_ADJACENCY]
            if any(
                re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", window)
                for t in subs
            ):
                hits += 1
        if hits > best_hits:
            best_family, best_hits = name, hits
    return best_family, best_hits


@dataclass
class PageHit:
    doc_id: str
    filename: str
    book: str
    section: str
    score: float
    snippet: str
    marker_page: int
    printed_page: int | None
    printed_source: str  # "footer" | "none"
    terms_present: int
    ruling_shape: str = ""
    ruling_hits: int = 0
    excerpt_source: str = ""  # "shape" | "subject" | "head"
    subject: str = ""         # the rarest content term; must appear in the excerpt
    edition_tag: str = "SR3"

    def citation(self) -> str:
        if self.printed_page is not None:
            return f"{self.book} p.{self.printed_page}"
        return f"{self.book} OCR page {self.marker_page} (printed page not legible)"


def _printed_page(body: str) -> tuple[int | None, str]:
    for pat in _FOOTER_RES:
        m = pat.search(body)
        if m:
            try:
                return int(m.group(1)), "footer"
            except ValueError:
                continue
    return None, "none"


def _page_units(scope: str = "sr3_rules") -> Iterable[tuple[Path, int, str, str, str]]:
    """Yield (doc, marker_page, body, book, section) for every page of the rules corpus."""
    rules_root = MEMORY_ROOT / "00_sources" / "rules_references"
    if not rules_root.exists():
        return
    for doc in sorted(rules_root.rglob("*.md")):
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        parts = PAGE_MARKER_RE.split(text)
        if len(parts) < 3:
            continue
        rel = doc.relative_to(rules_root)
        section = rel.parts[0] if len(rel.parts) > 1 else ""
        book = rel.parts[-2] if len(rel.parts) > 1 else doc.stem
        for i in range(1, len(parts) - 1, 2):
            try:
                marker = int(parts[i])
            except ValueError:
                continue
            body = parts[i + 1]
            if len(body) >= _MIN_PAGE_CHARS:
                yield doc, marker, body, book, section


def _ruling_window(body: str, terms: list[str], families, span: int = 900) -> tuple[str, str]:
    """Choose which part of a page the table actually hears, and what justified it.

    Returning the first 900 characters of a page is how the equipment tier's own bug
    behaved one layer up: a page whose heading is "WEAPON RANGE TABLE" and whose ruling
    sits 2,000 characters down reads as a page about whatever the heading says. Anchor on
    the ruling shape when one matched, else on the most frequent content term, else on the
    heading (a table's caption is often the only useful line).
    """
    low = body.lower()
    anchor = -1
    source = "head"
    if families:
        for name, pat in families:
            cues = next((c for nm, _p, c in _RULE_SHAPES if nm == name), ())
            subs = [t for t in terms if len(t) >= 4 and t not in cues and t not in _STOP_TERMS]
            for m in pat.finditer(body):
                lo = max(0, m.start() - _RULING_ADJACENCY)
                window = low[lo:m.end() + _RULING_ADJACENCY]
                if any(
                    re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", window)
                    for t in subs
                ):
                    anchor, source = m.start(), "shape"
                    break
            if anchor >= 0:
                break
    if anchor < 0:
        scored = [
            (_term_count(low, t), i)
            for i, t in enumerate(terms)
            if len(t) >= 3 and t not in _STOP_TERMS
        ]
        if scored:
            best = max(scored)
            m = re.search(
                r"(?<![a-z0-9])" + re.escape(terms[best[1]]) + r"(?![a-z0-9])", low
            )
            if m:
                anchor, source = m.start(), "subject"
    if anchor < 0:
        return re.sub(r"\s+", " ", PAGE_MARKER_RE.sub(" ", body[:span])).strip(), "head"
    start = max(0, anchor - span // 4)
    end = min(len(body), start + span)
    return re.sub(r"\s+", " ", PAGE_MARKER_RE.sub(" ", body[start:end])).strip(), source


# An adventure module is not a rules source, and fan material is not SR3 canon. Filtered
# during the walk, not after the limit: the rules tier previously cut adventures after
# ranking, so a module occupying a top slot simply cost the retrieval its best candidate
# instead of being passed over. Shared with the bridge so both agree on what a ruling may
# cite.
RULES_EXCLUDED_SEGMENTS = ("/adventures/", "/scenarios/", "/fan/", "/indexes/", "/misc/")


@dataclass
class PageAnswer:
    """A retrieval decision, not just a ranked list.

    The live wake path needs an accept/decline, and it needs to say why. Ranking alone
    caused the failure this whole layer exists to fix: a tier that injects whatever is
    first will eventually speak a fluent wrong ruling with a confident citation, which
    costs the table more than "I can't pull that citation this turn".
    """

    query: str
    accepted: bool
    reason: str
    hits: list[PageHit]
    responsive_books: list[str]


def page_answer(
    query: str,
    scope: str = "sr3_rules",
    limit: int = 6,
    exclude_segments: Iterable[str] | None = None,
    min_responsive_books: int = 2,
    excerpt_budget: int = 900,
    shape_allowlist: tuple[str, ...] | None = None,
) -> PageAnswer:
    """Decide whether the corpus can answer this rules question, and from which pages.

    Acceptance requires agreement between at least `min_responsive_books` distinct books,
    where a book counts as responsive only if the ruling text is actually inside the
    excerpt that would be spoken. That is the corpus skill's rule made operational -
    "multiple SR3 books agreeing is corroboration only when they agree on responsive
    text" - and it is what the book-level scorer could never express, because at book
    granularity everything agrees with everything across 350 pages of boilerplate.

    Measured on scripts/rules_eval.py: requiring >=2 responsive books accepts 5 of 7
    accept cases at 100% precision and correctly declines the 2 that would have been
    wrong (a Year of the Comet SURGE "3D6" table answering a drain-dice question, and an
    Aimed Shot page answering a complex-action target number). Both of those had zero
    responsive books. Recall is deliberately traded for precision: a decline costs a turn
    of "check the table", a wrong accept costs the table a false rule.
    """
    hits = page_search(
        query=query,
        scope=scope,
        limit=limit,
        exclude_segments=RULES_EXCLUDED_SEGMENTS if exclude_segments is None else exclude_segments,
    )
    if not hits:
        return PageAnswer(query, False, "no_pages", [], [])

    # A page is responsive only if it either carries a ruling shape next to the subject, or
    # carries enough of the query's content terms to plausibly state the answer. Shape is
    # checked here rather than trusted from ranking, so ranking can never be the only net.
    terms = _query_terms(query)

    def responsive(h: PageHit) -> bool:
        # The spoken excerpt, not the whole page, must carry the asker's distinctive term.
        # Ranking already dropped pages that lack it; this catches the case where the
        # 900-character window was anchored elsewhere and would read the answer away from
        # the subject. Then either a ruling shape sits next to the subject, or the excerpt
        # carries enough of the query to plausibly state the answer.
        if h.subject and h.subject not in h.snippet.lower():
            return False
        if RULES_REQUIRE_SHAPE:
            # Stricter mode for measurement: a shape must sit next to the subject. On OCR'd
            # prose a shape alone is weak - a damage code appears in fiction paragraphs,
            # "3D6" heads a random SURGE table - so this asks whether shape can carry any
            # weight or whether corroboration is doing all the work.
            return h.ruling_hits >= 1
        if h.ruling_hits >= 1:
            if shape_allowlist is not None and h.ruling_shape not in shape_allowlist:
                return False
            return True
        # No shape matched. Prose pages are admitted only with corroboration, which the
        # caller enforces via min_responsive_books.
        if shape_allowlist is not None:
            return False
        return h.terms_present >= max(2, min(3, len(terms)))

    good = [h for h in hits if responsive(h)]
    books = sorted({h.book for h in good})
    if len(books) < min_responsive_books:
        return PageAnswer(query, False, f"only_{len(books)}_responsive_book(s)", good, books)
    top = good[0]
    if not top.snippet:
        return PageAnswer(query, False, "empty_excerpt", good, books)
    return PageAnswer(query, True, "corroborated", good, books)


def page_search(
    query: str,
    scope: str = "sr3_rules",
    limit: int = 6,
    exclude_segments: Iterable[str] = (),
) -> list[PageHit]:
    """Retrieve printed pages from the SR3 corpus, ranked as pages.

    Differences from keyword_search that are load-bearing, not cosmetic:

    1. The unit is a page, so the returned text IS the passage. No anchoring heuristic
       decides what the table hears; the whole page is scored and returned.
    2. IDF is computed over pages. "pistol" stops being worth the same as it is in a
       contents page once a weapons table is a competing candidate.
    3. A page must contain the most discriminative term present in the query. This is
       what makes a multi-book agreement claim mean something: each book had to answer,
       not merely mention.
    4. Co-occurrence is scored. Two query terms close together on one page is the
       strongest signal available without an embedding, and it is what separates the
       range table from a page that happens to say "pistol" and "range" apart.

    exclude_segments filters during the walk rather than after the limit. The rules tier
    previously cut adventures after ranking, so an adventure module occupying a top slot
    simply cost the retrieval its best candidate instead of being passed over.
    """
    q = (query or "").strip()
    if not q:
        return []
    terms = _query_terms(q)
    if not terms:
        return []

    banned = tuple(s.lower() for s in exclude_segments if s)

    class _Page:
        __slots__ = ("doc", "marker", "body", "low", "book", "section", "counts")

        def __init__(self, doc, marker, body, book, section, counts):
            self.doc, self.marker, self.body = doc, marker, body
            self.low = body.lower()
            self.book, self.section, self.counts = book, section, counts

    pages: list[_Page] = []
    for doc, marker, body, book, section in _page_units(scope):
        where = f"/{section.lower()}/{book.lower()}/"
        if banned and any(b in where for b in banned):
            continue
        low = body.lower()
        counts = [_term_count(low, t) for t in terms]
        if not any(counts):
            continue
        pages.append(_Page(doc, marker, body, book, section, counts))

    if not pages:
        return []

    n = len(pages)
    idf = [
        math.log((1.0 + n) / (1.0 + sum(1 for p in pages if p.counts[i] > 0)))
        for i in range(len(terms))
    ]
    df = [sum(1 for p in pages if p.counts[i] > 0) for i in range(len(terms))]

    # The subject is the asker's most distinctive word: the content term that occurs in
    # the fewest pages, measured over the corpus rather than guessed from a list. Measured
    # df over 3,171 rules pages: "glitch" 37, "soak" 6, "penalty" 102, versus "test" 1,081,
    # "many" 1,206, "number" 1,407. Requiring it in the excerpt is what separates a page
    # about the asked-about thing from a page about something else that shares a common word.
    # It also fixes the two leaks the first eval exposed: a Year of the Comet SURGE "3D6"
    # table answering a drain-dice question (no "drain" anywhere in it) and an Aimed Shot
    # page answering a complex-action target number (no "complex").
    #
    # Stop words and family cue words are excluded from candidacy, because "governs", "range"
    # and "damage" are vocabulary the shape matcher already consumes; letting them be the
    # subject is what promoted "Edged Weapons (Strength) governs..." to a stealth answer.
    cue_words = {c for _n, _p, cs in _RULE_SHAPES for c in cs}
    distinctive = [
        i
        for i in range(len(terms))
        if terms[i] not in _STOP_TERMS and terms[i] not in cue_words
    ]
    # Absence is a decline, not a fallback to the next-rarest word. Measured on the first
    # eval run: "how many dice for a countermagic test" has "countermagic" at df 0 across
    # all 3,171 pages, and because the absent term was simply dropped from candidacy the
    # subject became "test" (df 1,081) - which every page contains - so the gate passed a
    # dice-pool page about something else. The same happened for "soak" (df 6) and
    # "penalty" (df 102). The sr3-rules-corpus-lookup skill is explicit that a missing
    # grep hit is evidence about the corpus, not permission to approximate: a brand name
    # missing from the corpus stays a GM call.
    absent = [terms[i] for i in distinctive if df[i] == 0]
    if absent:
        return []
    if not distinctive:
        return []
    subject_idx = min(distinctive, key=lambda i: (df[i], -len(terms[i])))
    subject = terms[subject_idx]

    # Rank query terms by how much they discriminate, ignoring asker phrasing. The gate
    # below needs the top two to cover the subject; a single rare word cannot veto.
    order = sorted(range(len(terms)), key=lambda i: (-idf[i], -len(terms[i]), df[i]))
    topical = [i for i in order if df[i] >= 2][:2]
    if not topical:
        topical = order[:2]

    total_idf = sum(idf) or 1.0
    families = _rule_families(terms)

    hits: list[PageHit] = []
    for p in pages:
        present = [i for i, c in enumerate(p.counts) if c > 0]
        # Real topical overlap: at least two content terms, and at least one of the two
        # most discriminative ones. This is what makes a multi-book agreement claim mean
        # something - each book had to answer, not merely mention.
        if len(present) < min(_MIN_TERMS_PRESENT, len(terms)):
            continue
        if not any(i in present for i in topical):
            continue
        # The page must be about the asked-about thing, not merely contain common words.
        if p.counts[subject_idx] == 0:
            continue

        # Score is coverage of the query's IDF mass, so a page carrying "stealth" and
        # "attribute" beats one carrying "stealth" and "test". Saturating tf is kept for
        # repeat terms so a page that says "damage" 40 times in a table does not win by
        # density alone.
        coverage = sum(idf[i] for i in present) / total_idf
        tf = [1.0 + math.log(c) if c > 0 else 0.0 for c in p.counts]
        density = sum(t * w for t, w in zip(tf, idf)) / (total_idf or 1.0)
        norm = 1.0 + math.log10(max(1.0, len(p.body) / 400.0))
        score = (1.5 * coverage + density) / norm

        # Co-occurrence: all query terms near each other. This is the discriminator the
        # book-level score structurally could not express, and it is what separates the
        # range table from a page that says "pistol" and "range" 3,000 characters apart.
        if len(present) >= 2:
            positions: list[int] = []
            for i in present:
                m = re.search(r"(?<![a-z0-9])" + re.escape(terms[i]) + r"(?![a-z0-9])", p.low)
                if m:
                    positions.append(m.start())
            if len(positions) >= 2:
                spread = max(positions) - min(positions)
                if spread <= 200:
                    score *= 1.6
                elif spread <= 600:
                    score *= 1.25

        printed, source = _printed_page(p.body)
        family, shape_hits = _ruling_shape(p.body, terms, families)
        # Shape is a tiebreaker, not a booster. Three consecutive boost attempts (coverage
        # weight, then 1.9-2.4x, then the same with cue terms excluded) each promoted a
        # fluent page that was not the ruling: an archetype stat block, then
        # "Edged Weapons (Strength) governs..." as the answer to a stealth question, then
        # "OCT field agents are quickly passed on to their back-up" for a range question,
        # because "quickly" contains "quick" and the range_band pattern matched on it.
        # Anything that multiplies a score invites gaming; this ranks and reports instead.
        excerpt, excerpt_source = _ruling_window(p.body, terms, families)
        hits.append(
            PageHit(
                doc_id=_doc_id(p.doc),
                filename=p.doc.name,
                book=p.book,
                section=p.section,
                score=round(score, 4),
                snippet=excerpt,
                marker_page=p.marker,
                printed_page=printed,
                printed_source=source,
                terms_present=len(present),
                ruling_shape=family,
                ruling_hits=shape_hits,
                excerpt_source=excerpt_source,
                subject=subject,
            )
        )

    if not hits:
        return []
    # Rank on retrieval quality only. The tier that speaks the answer decides whether to
    # trust a page; ranking is not allowed to be the only safety net.
    hits.sort(key=lambda h: (-h.ruling_hits, -h.score, -h.terms_present, h.marker_page))
    return hits[: max(1, min(limit, 20))]


def get_doc(doc_id: str, max_chars: int = 8000) -> dict:
    doc_id = (doc_id or "").strip().lstrip("/")
    if doc_id.startswith(WIKI_PREFIX):
        base, rel = CAMPAIGN_WIKI_ROOT, doc_id[len(WIKI_PREFIX):]
    elif doc_id.startswith(WORKSPACE_PREFIX):
        base, rel = WORKSPACE_ROOT, doc_id[len(WORKSPACE_PREFIX):]
    else:
        base, rel = MEMORY_ROOT, doc_id

    p = (base / rel).resolve()
    root_resolved = str(base.resolve())
    if str(p) != root_resolved and not str(p).startswith(root_resolved + os.sep):
        raise ValueError("doc_id outside permitted roots")

    if not p.exists() or not p.is_file():
        # Agents commonly guess a bare filename from a search hit; resolve by name so
        # a follow-up read costs one round trip instead of a re-search.
        needle = Path(rel).as_posix()
        for cand in _iter_docs("all"):
            cand_posix = cand.as_posix()
            if cand.name == Path(needle).name or cand_posix.endswith("/" + needle):
                p = cand.resolve()
                break

    if not p.exists() or not p.is_file():
        raise FileNotFoundError(doc_id)

    text = p.read_text(encoding="utf-8", errors="replace")
    return {
        "doc_id": doc_id,
        "filename": p.name,
        "path": str(p),
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def upsert_fact(payload: dict) -> dict:
    FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    now = int(time.time())
    row = {
        "ts": now,
        "fact": payload.get("fact", "").strip(),
        "entity": payload.get("entity", "").strip(),
        "source": payload.get("source", "discord"),
        "channel": payload.get("channel", ""),
        "confidence": payload.get("confidence", "medium"),
        "tags": payload.get("tags", []),
    }

    with FACTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    audit = {
        "ts": now,
        "action": "upsert_fact",
        "filename": FACTS_FILE.name,
        "entity": row["entity"],
        "source": row["source"],
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit, ensure_ascii=False) + "\n")

    return {"ok": True, "written": str(FACTS_FILE), "audit": str(AUDIT_FILE)}


def queue_entity(payload: dict) -> dict:
    queue_file = MEMORY_ROOT / "entity_request_queue.jsonl"
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    row = {
        "ts": now,
        "entity": payload.get("entity", "").strip(),
        "note": payload.get("note", "").strip(),
        "status": "incoming",
        "source": payload.get("source", "openclaw"),
    }
    with queue_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True, "written": str(queue_file)}


def _start_service(cmd: list[str], log_name: str) -> dict:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = AUDIT_DIR / log_name
    with log_path.open("a", encoding="utf-8") as logf:
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=logf, stderr=logf, start_new_session=True)
    return {"pid": proc.pid, "log": str(log_path), "cmd": " ".join(cmd)}


def restart(service: str = "all", wiki_port: int = 8889, api_port: int = 8091) -> dict:
    service = (service or "all").lower()
    actions = []

    if service in {"all", "wiki"}:
        pat = str(REPO_ROOT / "05_serving" / "knowledge_wiki_server.py")
        subprocess.run(["pkill", "-f", pat], capture_output=True)
        started = _start_service(
            ["python3", str(REPO_ROOT / "05_serving" / "knowledge_wiki_server.py"), "--port", str(wiki_port)],
            "knowledge_wiki_server.log",
        )
        actions.append({"service": "wiki", "status": "restarted", **started})

    if service in {"all", "api"}:
        pat = str(REPO_ROOT / "05_serving" / "memory_api_server.py")
        subprocess.run(["pkill", "-f", pat], capture_output=True)
        started = _start_service(
            ["python3", str(REPO_ROOT / "05_serving" / "memory_api_server.py"), "--port", str(api_port)],
            "memory_api_server.log",
        )
        actions.append({"service": "api", "status": "restarted", **started})

    return {"ok": True, "service": service, "actions": actions}


def rebuild(target: str = "", scope: str = "all") -> dict:
    scope = (scope or "all").lower()
    cmds: list[list[str]] = []

    kb_cmd = ["python3", str(REPO_ROOT / "03_organization" / "build_campaign_kb.py")]
    if target.strip():
        kb_cmd += ["--target", target.strip()]

    if scope in {"all", "campaign", "entity"}:
        cmds.append(kb_cmd)
    if scope in {"all", "campaign"}:
        cmds.append(["python3", str(REPO_ROOT / "03_organization" / "build_entity_manifest.py")])
        cmds.append(["python3", str(REPO_ROOT / "03_organization" / "build_campaign_intro_timeline.py")])

    ran = []
    for cmd in cmds:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        ran.append({
            "cmd": " ".join(cmd),
            "code": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        })
        if proc.returncode != 0:
            return {"ok": False, "target": target, "scope": scope, "runs": ran}

    return {"ok": True, "target": target, "scope": scope, "runs": ran}
