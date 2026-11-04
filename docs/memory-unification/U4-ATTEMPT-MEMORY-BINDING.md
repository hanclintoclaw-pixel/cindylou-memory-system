# U4: uninstalled attempt-owned pairing candidate (Packet 32)

## Scope and policy

This packet adds a **default-off, uninstalled lifetime binder**, not a memory reader.
It applies after Packet28's cleanup candidate and Packet29's narrowing correction,
against host `4d94a9fac61f2e83331a09df18ad35cdfb1faf5c`. Packet31's executor
remains unchanged and is **not connected** to this binder. No provider, worker,
IPC, session source or database is acquired by the new code.

The changed complete dispatch module supplies the resolver-returned audience and
original validated admitted context directly to a host-private wrapper. The wrapper
uses the corrected audience-custody helper, so all fallible pairing setup is under
cleanup coverage. A frozen opaque handle indexes a module-local WeakMap record;
identity comparisons reject copied handles and crossed otherwise valid pairs.
Current admission and audience assertions remain necessary, not sufficient authority.
The record expires in an inner finally before attempt controls close and before the
resolver's release callback. Borrowed audiences retain the resolver's no-op release.
Nested cleanup still runs release/abort-clear after a close/release failure; later
cleanup errors may mask earlier errors, as in the inherited helper.

The immutable shipped literal is false. It invokes the existing operation without
inspecting the pair or invoking authority assertions. There is no public enable
switch, wire mint, session-key lookup or legacy/lower-containment fallback.
Enabled tests replace exactly one asserted policy literal **inside a closed VM only**.
Real dependency import-time behavior is not exercised by synthetic imports.

## Evidence boundary

Tests execute the complete patched pinned dispatch and actual binder/helper modules
with closed synthetic imports. The wrapper instrumentation observes, but does not
substitute for, the exact pair supplied at the actual dispatch call. Enabled controls
exercise cross-pair/copy rejection, setup errors, backend rejection/settlement,
revocation, borrowed release and cleanup faults. Disabled controls exercise shipped
policy including poison captured objects and throwing authority mocks. Deliberately
broken VM-only variants remove pair comparison or record deletion; failures must be
assertion failures, not import/syntax failures.

Final controls pass **38/38**: 16 enabled complete-dispatch, 15 shipped-disabled,
and seven additional rejection/cleanup controls. The two broken variants fail five
and 15 controls respectively with expected assertion failures. The initial run and
original executed test are retained; strengthened current-audience mocks were fully
rerun without changing candidate/compiler source. 46 compiler/dispatch/control log
hashes were verified, plus the separate initial supplement receipt. Both fresh
standard core baseline/candidate checks exit zero with empty diagnostic logs.
All scratch patches reversed to original target bytes; selected installed source
hashes match. Packet31's 40 closure bindings were preserved through immutable
before-snapshots for mutable authority/restart/daily files. This is same-owner
source/receipt review, not independent-agent review or live acceptance.

Private receipts retain validators, source/log hashes, compiler inputs,
restoration and checkpoint bindings. Standard canonical core baseline and candidate
are separate from **declaration-enabled acceptance**, which remains open after the
retained Packet30 watchdog timeout. Reused dependency links do not freeze their
contents or prove active runtime/build identity. No install/codegen/emitted build.

## Still unavailable

This is a source-bound local pairing seam with no backend handle propagation or
executor consumption. The binder does not yet capture the attempt abort signal;
that must be added and negatively tested at the executor bridge. The inherited
abort-error substitution test is not signal-revocation proof. A synthetic pair is not real host issuance. Implementing this
seam does not clear actual authority integration, atomic participating effect-owner
commit/revocation, active dependency/build identity, compatible confinement,
whole-resource settlement, or production write denial. Both real reader lanes remain
unavailable. No quality/loss/parity/latency measurement or new source/claim clearance.
Prior counts and unresolved cases are unchanged. No production builds, readers,
provider imports, live probes, config/routing/voice changes, rights expansion,
promotion, restart/deploy/cutover, destructive retirement, index rebuild or U5.

Next bounded work: connect an opaque pairing handle to the admission-only executor
at a private attempt-owned call boundary without forwarding a wire-reconstructible
grant. Require exact handle identity, authority/caller alignment, abort/revocation,
setup failure and before-release invalidation; every read must still refuse before
request access. Independent corrected-candidate review remains an open gate before
any real integration. Sol/Medium; no new ETA.
