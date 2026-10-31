# U2 review — 2026-10-31

Requested by JackalMoreau before deciding whether to approve another public source
section or accept limited coverage. Thread is pinned to Sol/high. Reviewed HEAD:
`ccdc7c74202b6b16f9acbbd1ef7623513274e09b`, particularly `dd3547f` and `ccdc7c7`,
their dependencies, private shadow evidence, checkpoint claims, and relevant installed
native/legacy entrypoints. This is a review, not an implementation or cutover.

## Verdict

**Do not close U2 on the previous report.** There is useful working adapter code, but
the claim that only an operator coverage decision remains is incorrect. Source approval
cannot repair the evidence and integration defects below. Leave Curtis approvals and
production unchanged while repairing the engineering gates. A limited pilot may remain
useful; limited coverage must not be confused with successful fixed-fact nonregression.

## Findings blocking sign-off

### 1. The loss/orphan counts do not measure what the report claimed

Locations: `scripts/memory_unification_fact_review.py:37`, `:79`, `:91`, `:100`, `:124`;
`scripts/memory_unification_shadow_readers.py:292`.

The inventory is 91 qualifying lines from one page plus 17 JSONL rows, not a reviewed
set of 108 unique semantic facts. Twelve counted wiki lines are headings; 38 are table
rows, which require interpretation rather than automatic treatment as distinct facts.
Wiki identifiers hash page/section/line coordinates, not propositions, so duplicates
and moved lines are not reconciled. A positive test only requires the owning document
in the top eight for one automatically selected token; a miss does not establish that
the fact is unreachable. Unified reachability is asserted from manifest membership,
not demonstrated by query and bounded read. Inventory loading checks a reviewer label
but does not revalidate its stored corpus/manifest hashes.

Counterexample: the 50 build-section lines marked legacy-unreachable share a document
that the real entity search returns and the real legacy get reads in full, without
truncation. Thus the claimed 51 wiki units orphaned from both are probe misses, not
established source orphans. The JSONL source really is omitted by the Markdown walker;
that proves disconnected source ingestion, not absence of equivalent facts elsewhere.

**Withdraw “31 unique facts lost” and the wiki orphan conclusion.** Preserve the old
artifact as historical evidence. Replace it with revision-bound, reviewed claim units,
derivative-aware identity, explicit query/read receipts, and separate source exclusion,
ranking miss, unknown, and genuinely disconnected-source categories. Unknown is not false.

### 2. Specialist integration exists only inside the evaluation script

Locations: `scripts/memory_unification_shadow_readers.py:198`, `:228`, `:242`;
`unification/service.py:17`.

Both specialist sides directly call the same production functions. This is useful
preservation smoke evidence, but the wrappers are not wired into MemoryService's shared
domain-routing path. MemoryService has lexical/native search and registry get, not
rules/equipment adapters. The new scripts also have no focused tests in the existing
70-test suite. The report overstated this as completing the remaining U2 specialist work.

Implement the shared specialist interface/routing and test positive evidence,
decline/unavailability, admission tiers, and citation preservation through that interface.
Do not retune production specialist logic to satisfy the evaluation.

### 3. Legacy revisions and corpus fingerprints are insufficient

Locations: `scripts/memory_unification_shadow_readers.py:111`, `:173`, `:276`;
`scripts/memory_unification_shadow.py:117`, `:161`, `:206`.

The legacy revision resolver only tries memory-root-relative paths; it never decodes
wiki/workspace namespaces. The real approved wiki file exists, yet its returned revision
is null. The legacy `revisions_sha256` hashes filenames, not content revisions, and the
whole fingerprint is cached. A scratch-file counterexample confirms both the cached
fingerprint and the freshly recomputed revision digest survive a content edit. Unified
specialist fingerprints omit their DB/cache/source versions. End-of-run validation
checks the public partition, not the complete legacy/specialist generation.

Fix namespace resolution and record content/source/backend versions before and after
evaluation, rejecting drift. Compare approved evidence at section granularity; do not
make a whole mixed legacy page appear approved simply to avoid redaction. Preserve
safe specialist citation/revision evidence instead of only grading and then redacting it.

### 4. The gate does not verify the deep fact or a positive rules citation

Locations: `scripts/memory_unification_shadow.py:85`;
`docs/memory-unification/eval-cases.json`.

The deep-fact grader ignores `required_source_terms`. A response containing only the
expected document ID, with no fact text at all, receives retrieval status `correct`.
Approving any section of the expected page would therefore be able to turn that check
green without proving the required fact was retrieved. The pinned positive rules query
returns empty on both sides and is observe-only; the negative rules query proves a
decline, not preservation of a positive printed-page citation.

Verify the actual eligible passage with bounded get and a reviewed fact rubric. Add
at least one positive rules citation case through the real shared specialist adapter.
Keep generated-answer grading separate (it remains not assessed, appropriately for now).

### 5. “Read-only by construction / production untouched” was too broad

Locations: `scripts/memory_unification_shadow_readers.py:1`, `:152`;
installed OpenClaw `extensions/memory-core/src/cli-index-search.runtime.ts:202`,
`:254`, and `src/memory/manager-search-orchestration.ts:256`, `:369`.

The legacy native-operator branch launches the live native CLI. That CLI can record
short-term recalls when dreaming is enabled, and cli-purpose search can perform index
maintenance. Production git/config and equipment-cache checks do not cover these writes.
The wrapper also ignores top-level native warning/staleness information. This establishes
an unneutralized write path and an evidence gap, **not proof a particular historical run
actually mutated those stores**. No historical before/after receipt covers every such store.

Remove this out-of-scope branch from the paired pilot, or evaluate a separately controlled
snapshot with the write paths explicitly handled. Preserve warning/unavailable/stale states.
Do not rerun the live CLI just to test whether it writes.

## Additional reproducibility/interpretation issues

- `create_adapters(args)` ignores registry/partition arguments and uses hard-coded paths,
  while the harness validates the supplied arguments. These can describe different
  generations. Bind adapters/fingerprints/reviews to the same explicit generation and
  reject mismatches before I/O.
- Full legacy corpus versus one approved section is an intentionally asymmetric experiment,
  not equivalent public-authority corpus parity. Label that difference per backend/domain.
- The original 20-query calibration list/results are not linked as a retained artifact.
  The correction acknowledging overlap is sensible, but “best available” is not established
  by the retained evidence. A score floor is candidate filtering, not answer confidence.
  No operator blessing of 0.30 can replace broader, reproducible relevance evaluation.
- Warm samples in the previous run are **n=2**, after omitting the first of three calls.
  The reported p95 is a two-observation maximum, not a dependable full-wiki service p95.

## Fresh verification and what still holds

Private receipt:
`/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification/reviews/20261031T205525009858Z/review.private.json`.

- Existing suites: **70 Python and 3 Node tests pass**. These are valuable boundary tests;
  they do not cover the newly identified real-reader/metric defects.
- Repeated six non-operator pinned cases, three calls per side. Entity retrieval, the
  pinned absent-entity case, exact equipment admission, and rules decline reproduce.
  Deep-fact retrieval still fails unified; the positive rules case remains unassessed.
- Real native bounded read returns exact expected text at authoritative line 20;
  stale revision returns stale, unapproved get is denied, 201 lines is rejected,
  and the persistent child exits 0.
- Exact equipment remains VERIFIED with Damage 9M, printed citation `sr3.278`,
  and separately labeled PDF location p.280. This is one smoke case, not shared-path sign-off.
- Observed unified warm maxima: entity approximately 0.102s, equipment approximately
  0.035s, positive-rules-query empty response approximately 0.881s (n=2 each).
  These are experimental retrieval timings, not answer latency or production p95.
- A new, saved 20-query sample retains 8/8 content-related candidates at 0.30,
  rejects 10/10 nonsense probes, and still returns unrelated section candidates for
  2/2 plausible-but-unanswerable-by-this-partition queries. This is **not** a reproduction
  of the unavailable original probe list, nor evidence of answer correctness/optimality.
- Fresh before/after receipts show observed production repository HEAD/status/diff hashes,
  selected config/registry/manifest/cache/DB bytes and mtimes, and embedding listener
  unchanged. No source approval, partition rebuild, live caller/configuration change,
  service start/stop, or native-operator CLI was performed during this verification.
  This bounded observation does not retroactively prove historical global non-mutation.

## Recommended next work

Repair evidence generation and bind it to the actual shared read path; add regression
tests for these counterexamples, a positive rules case, and genuine bounded deep-fact
evidence. Then rerun the controlled paired evaluation with immutable receipts. Only
after that should the operator's source-coverage decision be used in assessing U2.
The coverage decision may be deferred; it is not the sole remaining engineering gate.
