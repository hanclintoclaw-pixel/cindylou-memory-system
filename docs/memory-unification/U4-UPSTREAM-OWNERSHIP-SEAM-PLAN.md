# Packet43 — upstream ownership implementation-seam plan

**Source-only plan, not a patch or execution clearance.** Builds on Packet42's
independent acceptance of the corrected, literal-disabled synthetic fixture.
Pinned host source: `4d94a9fac61f2e83331a09df18ad35cdfb1faf5c`. Seven frozen files
and bounded line windows are recorded privately in `packet43-20261104`.
This is not a complete authority-writer inventory, loaded identity proof or SDK API.

## Smallest proposed implementation contract

One explicitly declared scratch-store operation, on an exclusively owned fresh
outermost connection, under a complete host-owned authority cohort. Reject unknown
writers, nesting, extra stores/sinks, unsupported resource lifetime or missing identity
before opening the effect store. This operation is not an arbitrary memory search.
Do not admit writable production state merely because commits can be ordered.
The strict comparison lane still requires production-write denial and confinement.

The host retains actual admitted authority; a worker receives an operation handle
bound by its retained authenticated owner/channel, not a serialized audience that
claims authority. Host-side reservations cover the whole exact transaction through
trusted settlement. The synchronous native COMMIT path must consume its one-use
transaction-bound permit without needing an async lifecycle lock held by a revoker.
No new public enable option, runtime import or integration is part of this plan.

## Concrete change map and obligations

1. **Attempt custody:**
   `src/agents/embedded-agent-runner/run/attempt-memory-audience.ts:18–64` returns a
   no-op release for a borrowed host-minted audience and the actual resolution release
   for an owned audience. Preserve this distinction. Future binding must start from
   the admitted attempt and retain the composite lane/attempt cancellation contract,
   not reconstruct authority from session/sender strings. This window does not trace
   every caller or establish handoff/final-release closure; those remain required.
2. **Plugin pending-close/effective completion:**
   `src/plugins/registry-lifecycle.ts:277–347` deletes epochs, marks records and
   quiesces/aborts instances synchronously; `:412–414` directly marks a record revoked.
   These are change points, not existing drain APIs. A proposed host-owned async drain
   must first close new effect ingress and deny delivery, then join retained native
   reservations before announcing the new protocol's effective-revocation completion.
   Do not silently redefine existing synchronous revoke semantics or return promises
   to unmodified callers. Inventory record revoke, registry retirement, replacement
   activation and instance-quiesce callers before choosing the API migration. Unknown
   callers must keep this lane unavailable. Retain immediate legacy denial; distinguish
   it explicitly from the new protocol's drain-complete linearization event.
3. **Session mutation participation:**
   `src/sessions/session-lifecycle-admission.ts:206–320` normalizes/sorts identities,
   tracks active mutations, can close work admissions, and awaits finalization before
   removing ownership. Join the same declared cohort across every participating session
   authority writer. Do not wait for a worker while holding an identity lock that its
   host admission needs. The generic finally removes mutation ownership even when
   finalization throws; do not equate that removal with trusted native settlement.
   Unknown settlement needs a separate retained quarantine/exclusion owner. This read
   does not prove all session/access/source-generation writers use this function.
4. **Worker reservation transport:**
   `src/infra/sqlite-worker-operation-admission.ts:129–135,232–247,480–505` distinguishes
   REQUESTED/REFUSED/GRANTED. A post-grant refusal records cleanup failure rather than
   retracting permission. Add a separate retained reservation binding to the actual
   owner, worker generation, connection, outer transaction, immutable intent and nonce;
   do not reinterpret the existing grant CAS as a commit-spanning fence. Both authority
   owners must retain their reservations before grant and until trusted settlement.
   Loss of port/worker or restart cannot release them by timeout or new JS generation.
5. **Native transaction consumption:**
   `src/infra/sqlite-transaction.ts:378–443` takes SAVEPOINT/RELEASE when a transaction
   is active, without calling `withCommit`; only the outer branch wraps actual COMMIT.
   A future narrow entrypoint must serialize the no-active-transaction check and BEGIN
   under exclusive connection custody, reject nesting before permit/effects, and bind
   the exact newly created transaction. Do not globally remove supported savepoints
   from the generic helper to make this narrow lane work. Declared outer transaction
   ownership must survive retry and commit failure, not be inferred from a callback.
6. **Effect-owner adapter:**
   `extensions/memory-core/src/memory/manager-publication.worker.ts:150–200` invokes
   admit then commit, tracks entered/committed, and exposes a local connection settlement
   check. `:203–212` also shows schema commands affecting PRAGMAs around that transaction.
   A future adapter would consume the exact retained permit at actual COMMIT and report
   committed outcome separately from cleanup/settlement. Do not treat that local check
   as all-resource settlement or admit schema/bootstrap as an invisible side effect.
   `src/state/openclaw-agent-execution.worker.ts:321–355` checks file identity, restricted
   admission and canonical DB owner; the commit stage also ensures file permissions.
   These checks must be preserved, and their physical writes separately excluded or
   mediated. They do not replace authority-owner participation.
7. **Trusted reconciliation:**
   `src/infra/sqlite-worker-operation-admission.ts:439–476` separately posts deferred
   commit facts and native settlement. A future coordinator must authenticate the
   retained owner/channel and exact transaction identity, validate literal true for
   whole-resource settlement, and retain known committed truth across cleanup errors.
   Unknown remains quarantined with owner fences held. The fixture's callable `settle`
   or `reconcile` and a caller-supplied true are not an authenticated native report.
   Settlement transport, native backend checks and recovery ownership require their
   own trace; the message label alone is not proof.

## Implementation order and review gates

**Next bounded packet:** source-only authority-writer/caller coverage inventory for
plugin revoke/retirement/replacement and session lifecycle/generation mutation, anchored
to the same host revision. Classify routes as participating, excluded or unresolved;
list lock ordering and re-entry edges. Preserve failed path guesses as discovery limits,
not missing-capability evidence. Do not produce a supposedly complete coordinator while
foreign writers are unclassified. Review this plan/coverage before any native patch.

After that gate, a separately scoped uninstalled candidate could implement the
host-owned pending/drain API and one authenticated scratch-owner adapter. Its exact
source tests must cover effective-revoke-first and reservation-first, immediate delivery
denial, nested/competing BEGIN, each missing-owner mutant, copied/stale permits, delayed
commit after channel loss, both cancellation arms, true-only settlement, and committed
cleanup failure. Unknown settlement must not reopen ingress. These are future controls,
**zero executed here**; Packet42 synthetic counts are not native test credit.

Compiler/declaration checks need the existing isolated-host procedure and explicit
packet scope. Before any real lane: complete owner participation, actual admitted caller
authority, selected loaded/dependency/build identity, compatible containment, whole
resource settlement, production-write denial, source eligibility and declaration
acceptance must all be independently established. Cross-store transactions, fairness,
real timers/death/crash recovery and all-host closure are not promised by this plan.

## Verification and unchanged scope

Parent verified 432 inherited closure bindings and retained four beforeimages. Seven
host files were frozen and inspected in ten bounded windows; source hashes/size/mtimes
are checked again after the plan. Only source, data/hash, documentation and git checks;
no tests/build/compiler/declaration, real reader/provider/native/DB/worker/network or
live probe. Static source receipts are not evidence of active loaded runtime identity.
No host source edits, installation/restart/deploy, routing/config/voice/rights/promotion,
U5 or new ETA. Both real lanes unavailable; all actual cutovers and gates remain open.
301/301 source-read, 0 unread, 184 mixed tasks, 1,206 observations, 0 promoted,
unique claims unassessed, 32 partial summaries and 19 private cases/two groups unchanged.
HEARTBEAT/notifier outside scope, not newly attested unchanged. Stop after this plan
and its closure; no native implementation dispatched.
