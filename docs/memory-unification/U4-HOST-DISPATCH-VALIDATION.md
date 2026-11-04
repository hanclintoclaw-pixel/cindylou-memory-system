# U4 packet29 — isolated dispatch validation and type correction

2026-11-04; Sol / Medium. This is an uninstalled candidate, not a host cutover.

## What changed

Packet28 was recovered at `7ba369f0a01c51f89fd1cb6394b6001e39559d8a` /
checkpoint `b61ebaff-98c6-47f0-b51c-c9ddbc8f7a7c`; all 15 closure hashes matched
before work. No worker was running. Its original patch and failing evidence are
retained unchanged.

`integration-candidates/packet29/host-custody-type-fix.patch` is a two-line
follow-up to packet28's patch. Moving parameter construction into an async
callback lost TypeScript's narrowing of `params.admittedRunContext` at two sites.
Both now consume the existing, validated `admittedRunContext` local: the attempt
parameter and the Gateway context resolver. No cast, widened type, fabricated
authority or alternate authority owner is added. The parent and corrected source
hashes are pinned in `type-fix-binding.json`.

## Actual dispatch boundary

`dispatch-boundary.test.mjs` loads the complete pinned dispatch function and the
exact candidate helper using Node's TypeScript stripping and VM modules. All
other imports are closed synthetic modules; unconfigured operations throw.
Filesystem creation, session handling, admission, Gateway tools and backend are
mocked. No real host dependency, reader, provider or session module is evaluated.

Fourteen controls exercise success, control-construction failure, plugin-refresh
failure, parameter-construction failure, synchronous Gateway dispatch throw,
backend rejection, each cleanup failure, nested cleanup faults, abort-error
substitution, borrowed no-op custody and backend-promise ordering. Forwarded
parameters and Gateway resolver retain the same synthetic admitted-context object.
The original dispatch fails seven cleanup controls, demonstrating that the tests
distinguish the insertion from the pre-patch call site. Earlier helper-only tests
are not recounted as new tests.

These are mocked dispatch checks, not proof that the real resolver mints authority
correctly or that real worker/native/broker resources settle. The operation's
promise is the only settlement barrier tested. Cleanup errors can still mask
earlier errors. A constructor that throws before returning owns any internal
allocation cleanup. Failures before audience acquisition remain outside this patch.

## Isolated source and compiler evidence

The host's pinned HEAD was archived into private scratch; neither patch was applied
to the host. Compiler runs use `tsconfig.core.json`, `--noEmit` and disabled
incremental state. This covers the host's core graph, not all UI/extension/test
projects or a production build. The installed compiler/dependency tree is reused
for static resolution, not executed by the dispatch tests and not globally frozen.

The first compiler attempt started before extraction finished and could not find
the compiler. It is retained as a failed preflight, not a typecheck. The completed
archive initially lacked two generated type declarations and two workspace-local
dependency links. Those existing declarations were copied and dependency links
added only in scratch; no database, generator, install script or build was run.
Original incomplete-environment diagnostics are retained separately.

The initial comparison exposed the two genuine candidate narrowing errors.
Supplemented source-config diagnostics also include declaration-name portability
and exported-anonymous-class errors outside this candidate; changes in those
diagnostics are not repairs attributable to this patch. Exact outputs, compiler
options, source hashes and original-code negatives are retained privately.

Final corrected outcomes, verified from the private receipt and exact log hashes:

- All 14 dispatch controls pass; the original-code negative rejects seven controls.
- The full source-config core check exits 2 with 607 diagnostics, exactly matching
  the supplemented baseline after line/column normalization; zero added or removed
  diagnostic lines. Neither candidate source file has a remaining diagnostic.
- The explicitly supplemental semantic-only core check (`--declaration false`)
  exits 0. This does not clear the full source-config declaration gate above.
- Both patches reverse cleanly to the pinned original source; the scratch helper
  is removed. The installed host target and the two supplied generated declaration
  sources retain their recorded bytes.
- Initial failed preflight, incomplete-environment runs, uncorrected candidate
  errors and original-code negative controls remain retained, not replaced.

## Reproduction and remaining gates

`validate-isolated.py <private-packet29-root> [receipt-prefix]` checks the original
packet28 patch against an archived source tree, retains exclusive-create logs,
executes dispatch and original-code negatives, and reverses the patch.
`validate-correction.py <private-packet29-root>` validates the follow-up and restores
the target source after checks. It records full source-config checks separately
from an explicitly supplemental `declaration=false` semantic-only check; the latter
must never be represented as the full source-config gate passing.

Next bounded validation: resolve/reproduce the full-config declaration failures
using a checkout-local static dependency layout and the canonical host compiler
entrypoint in isolation. Do not mask them with type widening or treat the
semantic-only success as acceptance. Review the corrected candidate before any
new host integration; no live application is authorized by this packet.

Actual authority-executor integration, participating effect-owner atomic protocol,
active dependency/build identity, compatible confinement, whole-resource settlement
and production-write denial remain open; both real reader lanes remain unavailable.
No production routing/config/voice/restart/deploy/cutover/U5, rights expansion,
promotion, private session/raw transcript reading or retrieval-quality/loss/parity/
latency measurement occurred. No source-review credit is added. Existing 301/301
read, 0 unread, 184 mixed tasks, 1206 observations, 0 promoted, unassessed unique
claims, 32 partial summaries and 19 unresolved cases in two origin groups remain.
Parent HEARTBEAT/notifier are untouched. No new ETA.
