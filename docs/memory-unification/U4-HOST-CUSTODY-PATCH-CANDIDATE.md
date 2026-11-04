# U4 packet28 — uninstalled host custody patch candidate

2026-11-04; `openai/gpt-6.1-sol`, thinking medium.

## Scope and result

Packet27's completed independent parent review was recovered, not repeated:
18 original bindings (including immutable authority snapshots) and 7 final-closure
hashes match; exact clean HEAD was `0a4a721`. Accepted fixture-only is not live
integration clearance. The operator's renewed continue request authorizes this
separately scoped, reversible staging step.

`integration-candidates/packet28/host-custody.patch` now targets the actual
`run-attempt-dispatch.ts` call site, plus a new host-private cleanup helper.
It is an artifact in this project, NOT applied to the installed host. The exact
source SHA-256 is pinned in `target-binding.json`; drift must reject application.
No runtime flag, provider route or installed code was changed.

Immediately after the existing audience resolver returns, the candidate enters
the helper's try/finally before control creation or further setup. The exact
resolver-returned release callback is retained, including its borrowed no-op.
Controls are registered immediately after successful construction. Nested
finalizers attempt controls-close, audience-release and abort-controller-clear
even if a prior cleanup throws. The original backend catch/error substitution
and post-compaction check remain; cleanup precedes the latter as before.

This is a concrete cleanup insertion candidate, not evidence that an existing
production leak occurred. A constructor that allocates internally and then throws
must own its own cleanup: the helper cannot close a handle never returned to it.
Later cleanup exceptions still mask earlier errors, explicitly tested; production
error aggregation is not solved. Waiting for the operation promise is NOT proof
that worker/native/broker resources have settled. No new executor is connected.

## Checks actually executed

- 11/11 Node tests execute the exact candidate TypeScript helper via Node's type
  stripping: setup/backend faults, each cleanup fault, nested faults, duplicate
  control registration, borrowed no-op and barrier-controlled release ordering.
- In a temporary private scratch directory, the patch passes `git apply --check`,
  applies, matches candidate/helper hashes, passes Node syntax checks for both
  files, and reverse-applies to exact original bytes with the added helper absent.
- Host target bytes match before/after verification. No host import or dispatch
  execution occurred. Syntax is not whole-host type checking or behavioral proof.
- Scoped git whitespace checks and a clean scoped commit are required at closure.

Reproduce without changing the host:
`python3 integration-candidates/packet28/verify-candidate.py <new-private-receipt-path>`.
The output is exclusive-create. Saved private verification contains exact commands,
outputs, exit codes and candidate hashes. An earlier direct 11/11 helper run also
passed; the recorded verification adds scratch application and syntax coverage.

## Remaining execution gates and next concrete step

Next: stage the patch into an isolated host checkout at the pinned source revision,
run whole-host type checking and actual dispatch-boundary mock tests (control
construction failure, plugin-refresh/setup failure, synchronous dispatch throw,
backend rejection, cleanup failure and borrowed custody). Do not apply or build
inside the running host. Fail source drift explicitly; retain the old candidate.
This is the next validation task, not a completed check in packet28.

Actual admitted-authority executor integration, participating effect-owner atomic
protocol, active runtime/dependency/build identity, compatible confinement, full
resource settlement and production-write denial remain OPEN. Both real lanes
remain unavailable. No reader/provider/native worker/private session/raw transcript,
production DB, HTTP/model/tool probe, rebuild/restart/deploy/cutover/rights expansion,
promotion/voice/config/destructive retirement/U5 is performed or authorized by
these tests. No retrieval quality, fact loss, parity or latency conclusion follows.

Source review totals remain 301/301 read, 0 unread, 184 mixed tasks, 1206 observations,
0 promoted, unique claims unassessed; 32 partial summaries and 19 private unresolved
cases in two origin groups are unchanged. No corpus review credit is added.
Preservation is limited to explicitly checked bytes/receipts, not a globally frozen
system. Prior evidence remains intact; mutable authority is snapshotted before its
new checkpoint. Historical High settings are not current effort; future work stays
Sol/Medium. Parent owns HEARTBEAT/notifier; neither is changed here. No new ETA.
