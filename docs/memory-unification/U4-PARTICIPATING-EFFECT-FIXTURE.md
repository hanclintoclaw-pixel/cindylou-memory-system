# U4 — participating-effect state-machine fixture (Packet39)

## Disposition and scope

**Implemented and self-reviewed synthetic fixture only; not independent code
acceptance or native integration clearance.** One fixed fake store, two fixed fake
authority owners (`plugin`, `session`), fresh outermost-only fake transaction,
opaque operation/permit/binding identities and separate pending/effective revocation.
No host, reader, provider, SQL, worker, network or production dependency is imported.
The fixture is under `tests/fixtures/`, not a production entrypoint.

The shipped `FIXTURE_POLICY_ENABLED` literal is false and checked before even
reading configuration. There is no enable argument/environment/config option.
The test harness replaces exactly this one asserted literal inside an isolated
Node VM module; imports from that VM are forbidden. Other shipped host/scaffold
policy literals were not changed. Node VM modules remain experimental: this is
a closed-import control harness, not a security sandbox or OS confinement proof.

## State and custody

Canonical acquisition is `plugin` then `session`, followed by exclusive fake store
check+BEGIN in the same synchronous, callback-free state-machine action. The cohort
is fixed and complete, not caller-selected. A prepared operation cannot bypass the
second already-active check at reservation. Tokens bind exact attempt, connection,
intent, outer transaction, nonce and store generation. Consumption requires the
original immutable binding object before inspecting any fields, excluding forged
copies and accessor re-entry. Permits/operations are WeakMap-held, single-use and
not reconstructible from serialized objects.

Reservation, permit consumption, successful fake C, resource settlement and effective
R are separate transitions. Pending revoke closes ingress immediately, but effective
R waits for retained holders. A winning grant can commit during drain; both attempt
and lane cancellation suppress delivery without pretending that C was rolled back.
Unknown resource settlement retains fences, quarantines the store and rejects new
transactions. A delayed fake-native C can still arrive in that state: exclusion is
retained until a separate explicit fake-owner reconciliation report. Known C cannot
be changed to rollback. Only explicit settled resources release the exact owned
reservation; borrowed attempt custody is never released. These are **fake owner
reports**, not authenticated native receipts or a real crash recovery mechanism.

No SQL/DML/BEGIN/SAVEPOINT/COMMIT is actually executed. The corresponding events and
logical commit counter model ordering only. No physical non-mutation, journal/WAL
behavior, worker liveness, IPC, actual timeout/death/kill, native settlement, fairness
or deadlock-freedom claim follows. Fixed synchronous acquisition excludes interleaving
by construction; it does not implement async multi-identity lifecycle locking.

## Executed controls

Final exact-source run: **30/30 tests pass**, including **six mutation-discrimination
tests**. Command:

```sh
node --experimental-vm-modules --test tests/test_participating_effect_fixture.mjs
```

Coverage of Packet37/38 specifications:

- Effective R first rejects before fake store open; grant first drains C before R,
  with pending-close ingress rejection and separate delivery suppression, for each owner.
- Attempt and lane cancellation before/after grant; instantaneous-abort mode refused.
- Cross-bound attempt/connection/intent/outer transaction/nonce/generation, foreign,
  copied/serialized handles, poison binding getters and duplicate consumption rejected.
- Commit then cleanup failure retains committed outcome; release only after resources
  settle. Without settlement, quarantine and retained ownership remain.
- Lost ACK/death/timeout are represented by the **same unknown report**, not three
  independently exercised mechanisms. Unknown rollback and delayed-C reconciliation
  are covered; contradictory outcomes and automatic release/reopening are rejected.
- Before-BEGIN refusal and modeled post-consumption rollback leave zero logical C.
- Second store/cache/background/file intents are denied, rather than implementing
  a second store. An already completed first C remains explicit and uncompensated.
- Competing prepared operations serialize on the fixed connection; acquisition order,
  exact-once owned release, borrowed no-release and pending revocation are checked.
- Missing fake runtime identity/source eligibility/cohort/recovery prerequisites and
  false policy deny before fake open. These booleans are not real prerequisite proof.
- Nested/already-active transactions reject before fake BEGIN, including a second
  prepared operation losing to an intervening fake BEGIN.

Six narrowly broken VM variants are required to throw the intended assertion, not
merely exit nonzero: grant/ACK early fence release; omitted plugin fence; omitted
session fence; settlement/savepoint-as-commit early release; omitted nested admission;
attempt-only delivery ignoring lane abort. The first four fail `C_BEFORE_EFFECTIVE_R`,
the fifth `NESTED_BEFORE_BEGIN`, the sixth `LANE_CANCEL_DENIES_DELIVERY`.
The early-release variant models the erroneous ordering; it does not execute SQLite
savepoints. The immutable test source records every exact-one-match transformation.

## Evidence and review limits

Private evidence: `packet39-20261104` under the memory-unification runtime root.
296 inherited Packet38 closure bindings plus 21 additional immutable/doc/current
bindings verified before mutation. Exact STATE/JOURNAL/RESUME/daily-note beforeimages
retained. All three test revisions and their stdout/stderr/command/source hashes are
preserved. Run1 passed31/31; run2 tightened binding identity and consolidated three
identical unknown labels into one case (29/29); run3 added delayed-C while quarantined
(30/30). Earlier runs are not evidence for the final changed code. Final source hashes
matched before and after execution. No failed test run occurred in this packet.
Initial broad context reads were truncated; no source-reading credit or absence
claim is based on those reads. A guessed review filename and shell glob were absent;
the actual committed review and checkpoint helper were subsequently read.

This is same-owner implementation/self-review. It adds executable fixture evidence,
not a new independent acceptance verdict. No host compiler/declaration/build, old
suite, native reader/provider/session/DB/worker, live probe or retrieval was run.
No quality/loss/parity/latency or newly observed production-wide preservation claim.
Only the fixture/tests, this report and appended RESUME are committed. No live
service/reader/routing/config/rights/voice/installation/restart/deploy/U5 changes.
HEARTBEAT/notifier outside scope, not newly attested unchanged. Packet35 patch EOF
whitespace and all older originals/failures remain preserved, not repaired here.

Both real lanes remain unavailable. Actual admitted host authority, complete native
owner participation, loaded/dependency/build identity, compatible confinement,
whole-resource settlement, production-write denial and explicit declaration acceptance
remain OPEN. Counts stay301/301read,0unread,184mixed tasks,1206observations,0promoted,
unique claims unassessed,32partial summaries,19private cases/two groups unresolved.

Next bounded action: independent source/code review of this exact fixture and its
control discrimination, including delayed C and nested ownership. Do not translate
fixture passage into host installation or real-reader execution. Further host work
must keep the upstream participation/identity/containment/settlement gates explicit.
Sol/Medium; no new ETA.
