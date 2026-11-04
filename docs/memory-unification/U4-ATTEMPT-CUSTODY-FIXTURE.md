# U4 packet27 — fixture-only attempt custody

Status: implemented and tested in a fake local fixture only. Real lanes unavailable.
Current project effort: `openai/gpt-6.1-sol`, thinking medium. Stop for parent review.

## Executable scope

`tests/fixtures/attempt-custody.fixture.mjs` is not exported by production and has
no host/provider/reader imports or IO. Each invocation requires literal
`enabled: true`; truthy substitutes do not activate it. Opaque WeakMap-minted fake
contexts, fixed fake loader/provider, counters and event barriers convey no real
host authority. Foreign, serialized and invented contexts are unavailable.
No public SDK extension or installed host boundary was changed.

Acquisition is immediately followed by try/finally, covering preparation failure.
Local attempt revocation/abort precedes settlement; nested finalizers close controls
and release an owned lease exactly once after acknowledged fake settlement, even
when post-settlement cleanup and control closing throw. Borrowed outer leases are
never released and their context remains usable until explicit outer revocation.
The synchronous scratch turnstile checks revocation then increments only its owned
counter without awaits/callbacks. It cannot fence an external mutation owner.

## Observed deterministic controls

Saved initial run: 20/20 passing. Saved final run: **21/21 passing**, zero failures,
cancellations or skips. Recovery inspected the unchanged full fixture/test code
and saved logs, and did not rerun completed tests. The logs do not contain
run-time source-hash attestations; recovery hashes bind the reviewed files now,
not retroactively their execution. The command is:
`node --test tests/test_attempt_custody_fixture.mjs`.

- Ownership: owned/borrowed success, preparation/provider/post-settlement cleanup/
  controls failure; exactly one owned release, no borrowed release; nested faults.
- Revoke-before-commit: an explicit event barrier holds after fake provider open;
  revocation followed by resumption leaves zero scratch effects.
- Settlement: an event barrier holds acknowledgement with pending work and zero
  releases; release follows settlement, including cleanup faults.
- Identity/registration: null, unknown or mismatched bundled identity and incomplete
  or truthy-string registration return unavailable before acquisition/provider open.

There are no sleeps, native workers, IPC, production opens or live probes.
Cleanup fault injection occurs AFTER acknowledged fake settlement; the fixture
neither simulates failed actual settlement nor establishes whole host resource
settlement. Concurrent real owners, real cancellation and real loader/build graph
identities are outside this prototype. Later cleanup errors mask earlier thrown
errors (explicitly asserted by the nested-fault test); this is not production error
aggregation. Synthetic success is not an authority or execution clearance.

## Evidence and preservation

Private packet27 receipts retain the prior interrupted attempt's baseline, state,
journal, both test logs and both preservation receipts unchanged. Recovery adds
revision-bound contiguous <=80-line/6000-character windows, code/log hashes,
selected preservation and checkpoint/closure receipts. Initial broad state/journal
context output was truncated; no source-review credit is assigned to it. All
seven decisive recovery windows were untruncated. No new source review credit.

19 private unresolved cases/two origin groups; 301/301 source-read, 0 unread,
184 mixed tasks, 1206 observations, 0 promoted, unique claims null and 32 partial
summaries remain unchanged. Prior receipts/failures/originals/import/OCR/quarantine
and selected production11dirty/caller/config/registry/two-sectionpilot/API38899
command/socket are preserved by selected hashes and observations, not global freeze.
Parent owns HEARTBEAT/notifier; neither edited nor attested unchanged.

## Remaining gates and stop

Actual host integration retaining admitted authority; participating-owner atomic
commit/revocation protocol; active runtime/dependency/build provenance; compatible
fork/thread confinement; whole descendant/resource settlement and all production
write-denial surfaces remain unproven. Real private/native lanes stay unavailable.
No real host patch, IPC, reader/provider/native worker, private sessions/raw
transcripts, model/HTTP/tool/live probe, production DB/build, import/rebuild/restart/
deploy, rights/promotion/primaryreader/routing/config/voice/destruction/U5 occurred.
No retrieval/get/paired-answer/quality/loss/public-parity/latency conclusion.
Stop packet27 for independent parent verification; no chained work or new ETA.
