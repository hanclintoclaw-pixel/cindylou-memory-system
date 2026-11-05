# U4 — participating-effect independent review and correction (Packet38)

## Disposition

**Independent narrow acceptance of the corrected design only.** Sol/Medium review
found a concrete omission in Packet37: an already-active same-connection SQLite
transaction takes SAVEPOINT/RELEASE and bypasses `options.withCommit`. Connection
identity and an inner helper return cannot establish outer native commit custody.

The appended [design correction](U4-PARTICIPATING-EFFECT-REVOCATION-DESIGN.md#packet38-correction--outermost-transaction-ownership)
requires a fresh outermost transaction, exclusive serialized connection check+BEGIN,
exact transaction-bound one-use reservation, and custody through outer settlement.
Already-active/nested transactions are rejected before effects; authenticated nesting
inheritance is outside scope. Nested rejection and savepoint/early-release mutant
controls are specified, not executed. The independent reviewer separately read and
accepted this addendum; its original required-correction report remains unchanged.

Conditional commit-before-effective-revocation ordering remains coherent only with
complete authority-owner participation. Pending close, effective revocation, native
commit and resource settlement remain distinct. Unknown settlement retains exclusion;
there is no instant-abort, timeout rollback, crash-recovery or cross-store guarantee.

## Evidence and actual checks

- Parent verified 296 inherited closure bindings, the original Packet37 closure hash,
  22 static host source hashes and four exact current mutable beforeimages.
- Two interrupted uncommitted review drafts were archived privately byte-for-byte,
  not treated as completed reviews. One historical draft claims Sol/high; that text
  was preserved, not rewritten or credited to this fresh Sol/Medium review.
- Fresh independent review inspected 17 host files, 25 bounded windows, 1,416 lines,
  plus original design and correction. Its 25 artifact hash/size bindings and final
  manifest hash were independently checked by the parent. Original design drift
  receipt is retained; separate correction receipt binds the new exact revision.
- Only source/document/hash/git checks ran. **Zero controls, tests, compilers,
  declaration retries, builds or real-reader executions.** The cross-device archive
  rename preflight failed before mutation; the corrected move and exact copies are
  retained. No old failed evidence was replaced.

Private review directory: `packet38-independent-20261105T023035Z` under the private
memory-unification runtime root. Parent recovery/closure directory:
`packet38-parent-recovery-20261104`. No private claim prose is published here.

Both literals remain default-off and uninstalled; both real lanes unavailable.
Actual host authority, native participating effects, active dependency/build identity,
compatible confinement, whole-resource settlement, production-write denial and
explicit declaration acceptance stay OPEN. Counts remain 301/301 read, 0 unread,
184 mixed tasks, 1,206 observations, 0 promoted, unique claims unassessed,
32 partial summaries and 19 unresolved private cases/two origin groups.
No production DB/provider/session/native-worker/live-probe/install/restart/deploy,
config/routing/voice/rights/promotion/retirement/rebuild/U5 changes or quality/loss/
parity/latency claim. HEARTBEAT/notifier outside scope, not newly attested unchanged.

## Next bounded action

The user's continuing staged-development instruction covers one default-off,
uninstalled single-fake-store/two-fake-owner coordinator fixture with deterministic
positive and narrowly broken negative controls. Include outermost-only transaction
ownership and all Packet37 discriminating specifications. No native host/reader/DB/
worker/provider/network path may be reachable. Passing synthetic controls will not
clear any real execution gate. This checkpoint does not start the fixture or schedule
a worker; resume that exact bounded action next, on Sol/Medium. No new ETA.
