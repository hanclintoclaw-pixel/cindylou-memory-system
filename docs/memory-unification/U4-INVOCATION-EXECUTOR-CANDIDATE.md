# U4 packet31 — default-off invocation custody candidate

2026-11-04; Sol / Medium. **Uninstalled, admission-only scaffold, not a usable
reader executor or completed host integration.**

Recovered packet30 commit `e0943e6a93affeb8e193696734a5465d334f0879`, checkpoint
`2d57ac84-4809-4989-97e8-bd0551971673`; verified all 48 closure hashes before
changes. Before authority/resume/daily bytes are retained privately.

## Implemented boundary

`integration-candidates/packet31/memory-invocation-executor.ts` stages the proposed
host-private `src/plugins/memory-invocation-executor.ts`. Its additive patch does
not change SDK exports, configuration, routing, a live caller or the host checkout.
It is compiled alongside the existing packet28+29 corrected cleanup candidate in
scratch; it does **not** add a call site to that dispatch yet.

The shipped policy is a literal false with no config/environment/public override.
The disabled factory returns before reading any argument property or evaluating
the lazy capture callback. In a deliberately enabled synthetic VM only, explicit
opt-in is also required. The candidate retains the exact admitted-run and caller
objects, obtains the existing admitted-run current assertion, requires a session
audience recognized by the host mint check, and uses the existing complete caller
currency assertion. Its opaque frozen handle is recognized only by a private
WeakMap: copies, JSON and other module-instance handles are not capabilities.

Changes to captured authority identity, session key/incarnation, audience, sandbox
bit, signal or caller assertion permanently deny a subsequent use. Admission,
audience and abort checks are repeated. Revoke/settle invalidate and forget local
custody; they never release the attempt owner's audience or close shared resources.
No provider/worker resources are allocated by the function. The small local handle
and WeakMap record are not a worker-settlement receipt.

Every read returns unavailable **before examining the request** because integration
prerequisites are missing. There is no provider-acquisition or fallback path,
including in the enabled VM. Errors return only fixed reason codes. This is not
an implementation of the wire parser, read/result schemas, transport turnstile,
request ledger, effect commit, identity receipt, confinement or resource joining.

## Tests and evidence limits

The complete exact candidate module executes with closed synthetic imports for
the two host authority modules; no real dependency graph or provider is evaluated.
The enabled controls replace exactly one immutable policy literal in the VM;
they do not demonstrate a shipped enable switch or actual host-issued admission.
Default-off control executes the unchanged literal. Import-time effects in the
real transitive host graph are **not tested** by those VM controls.

23 controls pass: default-off and opt-in laziness, exact identity retention,
copied admission/audience and operator/host rejection, wrong session binding,
revocation/abort, eight mutable-context substitutions, opaque handle rejection,
idempotent local teardown and error redaction. An initial console run and a later
saved run both pass; they are not 46 distinct controls.

Two deliberately broken VM variants fail: removing the disabled guard fails its
tripwire control; bypassing admitted-run resolution fails both exact handoff and
copied-admission controls. These expected failed runs and raw logs are retained.
This demonstrates control discrimination, not real authority issuance or provider
effect safety. All otherwise accepted synthetic reads remain unavailable.

Fresh canonical core checks exit 0 with empty stdout/stderr for both the unpatched
baseline and packet28+29 plus this additive candidate in the same restored Packet30
scratch environment. Command: `node scripts/run-tsgo.mjs -p tsconfig.core.json
--noEmit --incremental false`. The wrapper's standard declaration-disabled policy
is unchanged. All three patches reverse cleanly; the original dispatch bytes return
exactly and both new scratch modules are removed. Selected installed host source
hashes remain unchanged. The compiler's 606 recorded physical files, two supplied
declarations, generator stamp and dependency-link targets match Packet30's recorded
environment; measured static inputs are also unchanged across this run. Other
dependency contents remain reused, not frozen or runtime-attested.

The private validation receipt binds the exact executed validator/candidate, selected
host source, static compiler inputs and 22 raw log hashes. Same-owner post-execution
review verifies those log hashes and inspects both intentional failures; this is
not independent-agent review. No generator, install, database, emitted build,
declaration-enabled retry or whole-host/UI/extension/test acceptance is claimed.

## Concrete remaining handoff

Checking an admitted-run object and a separately valid audience does not establish
that those two grants belong to the **same** actual attempt. In particular, the
candidate does not yet bind the audience returned by
`resolveEmbeddedAttemptMemoryAudience` to the exact `admittedRunContext` retained
inside corrected `withAttemptAudienceCustody`. No fabricated caller/session IDs
can fill that gap. This is why a prepared synthetic handle is not a read capability.

Next bounded step: a source-bound, uninstalled attempt-owned binder at that exact
corrected dispatch lifetime. Bind the resolver-returned audience and original
admitted context as one private record; make cleanup invalidate it before releasing
the resolver's lease. Test the complete pinned dispatch with closed synthetic
imports, including crossed valid audience/admission pairs, setup failure, revocation,
borrowed no-op release and cleanup fault ordering. Keep all read dispatch unavailable;
do not add a public mint, serialized grant, provider call or routing/config change.
Do not mistake a static source binding or a VM-positive for real admission linkage.

The reached native owner still has unmediated recall/meta/origin/schema/cache and
worker effects. Existing generation facts are observations, not a participating
atomic commit fence. No new participant closes that protocol in this packet.
Actual host-executor integration, effect-owner atomicity, loaded dependency/build
identity, compatible confinement, whole-resource settlement and production-write
denial remain open; both real reader lanes remain unavailable. Declaration-enabled
acceptance also remains open with packet30's original 120-second timeout retained.

No live host installation, reader/provider/session execution, private transcripts,
production DB/build/probes/restart/deploy, rights expansion, promotion, routing,
voice, cutover or U5. HEARTBEAT/notifier untouched. Prior review/claim counts and
19 unresolved private cases/two origin groups are unchanged; no retrieval quality,
loss, parity, latency or new source-review claim. No ETA.
