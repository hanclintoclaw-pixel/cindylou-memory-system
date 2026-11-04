# U4 packet30 — canonical core compiler isolation

2026-11-04; Sol / Medium. Uninstalled candidate only.

## Recovered authority and scope

Recovered packet29 commit `7e068a6484228f0956a246bd11f49190e6570d9c`,
checkpoint `f3f3034e-1d7c-4f74-9bc7-f61afcd8a817`. All 71 packet29 closure
bindings matched before changes. Prior STATE/JOURNAL/RESUME/daily bytes are retained
privately before this checkpoint's append/update. No earlier test is recounted.

The question was whether the host's canonical core-check entrypoint reproduced
packet29's direct source-config declaration failures. This is not a production
build, UI/extensions/tests clearance, reader execution or live integration review.

## Compiler policy distinction

The pinned package's `tsgo:core` runs `scripts/run-tsgo.mjs` with
`tsconfig.core.json`. Its actual `applyLocalTsgoPolicy` implementation appends
`--declaration false` unless declaration checking was explicitly requested. The
source config itself has `declaration: true`. Packet29's direct compiler command
therefore checked a different declaration policy from the standard wrapper.

This is existing host policy, not a new override to make the candidate pass.
An actual `prepareTsgoCommand` observation records both effective commands:

- Standard: `--declaration false --singleThreaded --checkers 1`.
- Explicit declaration request: `--declaration true --singleThreaded --checkers 1`.

The wrapper preserves explicit declaration checking. Neither command alters the
source configuration. `--noEmit --incremental false` keeps this validation from
emitting a build or incremental cache; it still checks the core graph. The package
script's normal incremental cache is not exercised by this variation.

## Scratch environment

A new source tree was extracted from packet29's hash-bound archive of pinned host
HEAD `4d94a9fac61f2e83331a09df18ad35cdfb1faf5c`; extraction completed before checks.
The compiler package and Darwin ARM64 native compiler were copied physically into
this scratch checkout, satisfying the wrapper's existing compiler-path boundary.
No boundary code was modified. Compiler files are hash-bound before/after.

Other static dependency links remain reused from the installed dependency tree,
not independently frozen. The two existing generated Kysely declaration files were
copied with their recorded hashes; the generator content stamp was prepared in
scratch so the wrapper returns before SQL/code generation. This is supplied-type
compiler evidence, not a fresh schema-to-generated-type verification or dependency
provenance proof. No install, generator, database open, emitted build or provider
execution was needed. Wrapper tooling and scratch artifact-lock handling did run.

## Observed results and limits

The standard core check exits 0 with empty stdout/stderr for both original source
and the corrected packet28+packet29 candidate. This clears the **canonical core
compiler check in the recorded scratch environment**, not all host validation.

The explicit declaration-enabled candidate run hit the wrapper's 120-second
watchdog, exiting 1 with no diagnostic stdout. The wrapper reported killing the
compiler process tree. This is a timeout, NOT a reproduction of 607 diagnostics,
NOT zero diagnostics acceptance, and NOT a passing declaration check. The initial
validator's final assertion consequently failed; its source, receipt and raw
outputs are preserved. Both candidate patches nevertheless reversed successfully
to the exact original target, and the scratch helper was removed.

The committed validator subsequently separates declaration status from canonical
success and removes its inappropriate cross-checkout diagnostic comparison.
That reporting-only revision was syntax-checked, not end-to-end rerun. Execution
evidence binds the retained original validator, not the revised file.

Packet29's separate 607 baseline-equivalent diagnostics remain valid historical
evidence, not a new packet30 result. They were declaration-name portability and
exported-type diagnostics outside the candidate. Packet30 does not repair those
sources, claim fully local dependency resolution, or waive declaration acceptance.
The supplementary control confirms that the standard wrapper rejects the
uncorrected packet28 candidate with exactly one `TS2322` and one `TS2345`, exiting
2. Thus the standard command discriminates the actual type defect despite its
declaration policy. Its receipt is a distinct check, not an override of the
declaration timeout. The negative patch also reverses to the exact original bytes.

The installed host target retains its pinned bytes. Nothing was installed or
restarted. Packet29's reviewed fix passes the existing validated local admitted
context through the async callback; it neither mints authority nor widens types.
Its 14 mocked dispatch tests remain prior evidence, not rerun here. Real authority
and real worker/resource settlement are not established by this compiler packet.

## Continuation

Do not treat declaration diagnostics as a reason to refactor unrelated host
sources. Keep the declaration-enabled gate open; any future attempt must retain
this timeout and use a separately justified deadline/resource policy and a
same-environment original/candidate comparison, rather than comparing relocated
absolute diagnostic paths as if identical.

Next bounded task: stage the host-owned invocation/executor candidate specified in
`U4-HOST-INTEGRATION-PATCH-DESIGN.md` against the pinned source and corrected cleanup
candidate, with default-off behavior and closed synthetic imports. Validate exact
admitted-context custody and rejection before any provider access; do not execute
real readers or install the patch. If the effect-owner protocol cannot be made
atomic at the reached write boundary, keep that lane unavailable and record the
concrete missing participant rather than treating currency checks as a fence.

Actual authority-executor integration, participating effect-owner atomic protocol,
active dependency/build identity, compatible confinement, whole-resource settlement
and production-write denial remain open. Both real reader lanes remain unavailable.
No live probes, private sessions/raw transcripts, production DB/build/restart/deploy,
config/routing/voice/cutover/U5, rights expansion or promotion. Parent HEARTBEAT and
notifier are unchanged. Source/claim counts and 19 unresolved cases/two origin groups
remain unchanged; no quality/loss/parity/latency or new source-review claim. No ETA.
