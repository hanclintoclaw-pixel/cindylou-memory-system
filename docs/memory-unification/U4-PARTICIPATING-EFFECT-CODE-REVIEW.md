# Packet40 — independent fixture review

Verdict: **requires correction; no independent synthetic code acceptance**.
Reviewed Packet39 commit `5378f63a2158160837b69a2b66783e611838964c` under the
project Sol/Medium directive. This is not a production incident.

## Acceptance-blocking finding

Both `settle` and `reconcile` coerce `resourcesSettled` by truthiness. A string
`"false"` or an object can therefore release transaction custody and both owner
fences, clear quarantine and make pending revocation effective without an explicit
boolean settlement report. Require `resourcesSettled === true` in both paths;
malformed values must retain custody. The fake report origin remains assumed,
not authenticated native authority.

## Evidence

The reviewer read the complete fixture and test sources and the related design
and correction documents. Unchanged exact-source suite: **30/30 pass**, exit 0.
Eight independent adversarial probes: **four pass and four intended invariant
failures**, exit 1. These failures are preserved, not reported as passes.
Four negative probes cover string/object values in both settlement entrypoints.
The other probes cover strict boolean settlement, getter reentry, committed-outcome
preservation and opaque handle rejection. Fifteen review artifact hashes were
verified by the parent. Parent recovery also reverified all 358 saved bindings
against four exact mutable beforeimages where required.

Other bounded properties appeared coherent, including outermost transaction
ownership, complete fixed cohort, delayed C under quarantine, both cancellation
arms and targeted six-mutant discrimination. No all-input/formal correctness claim.
Original source, test logs, failed probes and reviewer report remain immutable in
private runtime evidence; this report does not overwrite Packet39's historical run.

## Boundary and next action

Next: one default-off fixture correction with malformed-settlement regressions and
narrow truthiness mutants, then independent exact-source review of the correction.
No host installation or native execution follows from this review. VM is not a
security sandbox. Both real lanes remain unavailable. Actual admitted authority,
complete native owner participation, loaded/dependency/build identity, compatible
confinement, whole native resource settlement, production-write denial and declaration
acceptance remain open. No new quality/loss/parity/latency, source-review, promotion
or U5 clearance. All claim counts/statuses remain unchanged. HEARTBEAT/notifier are
outside this packet; no new attestation about them.
