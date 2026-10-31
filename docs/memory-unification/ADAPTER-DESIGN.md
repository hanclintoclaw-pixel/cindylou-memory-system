# Persistent native adapter — pinned interface (U2)

Status: design contract for the U2 persistent adapter. No production caller uses this.
Authority remains `local operator.read` over an **entirely public** isolated partition only.
This is not a host-minted session lease and not a supported public extension API.

The spike (`scripts/memory_public_native_spike.mjs`) proved the capability in a
throwaway per-query process. This adapter makes the same lease persistent. Do not
re-run the spike to "confirm" it; its receipts are referenced by STATE.

## Two halves, one boundary

1. `unification/native_adapter.mjs` — long-lived Node process holding the lease.
   Reads one JSON request per stdin line, writes exactly one JSON response per
   stdout line. Lifecycle verbs only: `hello`, `search`, `get`, `health`, `ping`,
   `shutdown`. Never exits on a bad request; replies `{"ok":false,"error":...}`.
2. `unification/native_client.py` — implements the existing `NativeReader` protocol
   in `unification/service.py` so `MemoryService(mode="hybrid")` can consume it.
   Owns the child process, request ids, timeouts, and teardown.

The Python side never imports OpenClaw. The Node side is the ONLY place the
private-local facade is imported, so the version pin lives in exactly one file.

## Pinned facts — pass these through verbatim, do not re-derive

- OpenClaw runtime root: `/Users/hanclaw/claw/openclaw`
- Pinned revision: `4d94a9fac61f2e83331a09df18ad35cdfb1faf5c`
- Facade module: `dist/plugin-sdk/memory-host-search.js`
- Exports used: `getActiveMemoryProvider({cfg,agentId,purpose,context})`,
  `closeActiveMemorySearchManagers(cfg)`
- Lease context: `{authority:{kind:'operator',scopes:['operator.read']},
  assertCurrent(){...}}`, `agentId:'pilot'`, `purpose:'cli'`
- Isolation env set by the Python parent BEFORE spawning: `OPENCLAW_STATE_DIR=<partition>/state`,
  `OPENCLAW_CONFIG_PATH=<partition>/openclaw.json`. Inherit no other `OPENCLAW_*` variable.
- Node is launched with cwd anywhere, but the adapter must re-assert the env check
  before importing the facade, exactly as the spike does.
- Existing loopback embedding endpoint used by the pilot config:
  `http://127.0.0.1:52182/v1`, model `embeddinggemma-300m-qat-q8_0`, `fallback:'none'`.
  The adapter must NOT start, stop, restart, or reconcile that service.

## Required behavior (each item is a test)

- **Pin gate.** `git -C <runtime> rev-parse HEAD` must equal the pinned revision
  before importing the facade. Mismatch → refuse to start, exit non-zero, no lease.
- **Config gate.** Re-check the same unsafe-config conditions the spike rejects
  (workspace/agentDir, `sources == ['memory']`, `rememberAcrossConversations false`,
  `experimental.sessionMemory false`, empty `extraPaths`, loopback-only
  `remote.baseUrl`, `provider 'openai-compatible'`, `fallback 'none'`, no `models`
  key). Any failure → refuse to start.
- **Strict minScore at our boundary.** Raw native hybrid search admits lexical
  fallback below the requested threshold (`extensions/memory-core/src/memory/hybrid.ts:270`).
  Route every result page through `enforceMinimumScore` from
  `unification/native_contract.mjs`. Do not change production engine ranking.
  This is ordering-contract enforcement, NOT an answer-confidence gate.
- **Reference allowlist.** Every returned `reference.id` must be in the current
  generation's manifest. Anything outside → drop and count it.
- **Citations map back to authority, not to the projection.** A native hit names a
  disposable `memory/<sha256>.md` id. The response must carry the authoritative
  `doc_id`, `namespace/path#section_id`, full-file `revision`, `source_start_line` /
  `source_end_line`, `claim_status` and `authority` from the trusted registry — so a
  caller can never cite the projection as a source. Projection file names are derived
  by `unification/partition.py` as `sha256(doc_id) + '.md'`; reuse that mapping
  rather than inventing a new one.
- **Never mint claims.** `automaticRecall` must not be inferred or set. Transport
  `status` (`ok`/`denied`/`stale`/`unavailable`) stays separate from `claim_status`;
  retrieving a public provisional passage does not make it confirmed.
- **Bounded get.** Enforce `from >= 1`, `1 <= lines <= 200`, and verify the returned
  text starts with the expected source prefix. Native appends a continuation notice
  outside its structured source-line count — validate `from`/`lines` and the exact
  prefix, never total response newlines.
- **Revision revalidation on both sides of every operation.** Call
  `unification.partition.validate_public` with a **freshly reloaded** trusted
  registry before and after each search/get, as the probe does. On any edit,
  revocation, reclassification, coverage change, modified projection, added native
  root `USER.md`/`MEMORY.md`, or unexpected workspace file: fail closed with
  `unavailable` + `reason:'generation invalid; rebuild required'`. Never return a
  result from a stale generation, and never silently reuse an old projection.
- **Explicit failure states.** `unavailable` (child dead / lease closed / pin
  mismatch / generation invalid) must be distinguishable from `empty` (healthy
  search, zero hits) and from `stale` (revision drift). An empty success is not a
  substitute for an unavailable backend.
- **Revocation and teardown.** Respect host revocation: after the parent marks the
  lease stale, the next call must fail rather than return cached results.
  `shutdown`, `close()`, `closeActiveMemorySearchManagers(cfg)`, and child exit must
  all leave no orphan process. Closing the adapter must not leave a lease held.
- **Budgets.** Per-request timeout with a bounded wait (default 20s), a hard cap on
  in-flight requests (1 is fine), `maxResults <= 30`, query length cap 4000 to match
  `MemoryService.search`. A timeout marks the child suspect: after 2 consecutive
  timeouts, kill and restart once, then report `unavailable` rather than thrashing.
- **Honest coverage.** Propagate registry `coverage` and mark partial when any
  backend is not ready, matching `MemoryService._envelope`.

## Deliberately NOT in scope

- No production config change, no service restart, no listening socket, no RPC.
  Do not touch the live `memory-system` repo, the bridge, or `campaign-wiki`.
- No operator-RPC relay, no session audience, no per-document native permissions,
  no native `extraPaths`, no chat credential, no plugin install.
- No retuning of the SR3 rules/equipment specialists' decision logic and no
  changing printed page numbers (their adapters are the next step after this one).
- No changing `unification/policy.py` or `partition.py` to make tests pass. If a
  boundary test fails, the adapter is wrong.

## Tests

`tests/unification/test_native_client.py` must run **without** OpenClaw or the
embedding endpoint: drive a fake child process (a small Python stub echoing pinned
fixtures) through the same line protocol. Cover at least: pin mismatch refusal,
unsafe config refusal, minScore filtering, out-of-partition reference dropped,
citation rewritten to authoritative section+revision, stale generation fails closed
before and after I/O, empty-vs-unavailable distinction, timeout → restart-once →
unavailable, revocation rejects the next call, teardown leaves no child, and a
malformed/oversized request never kills the child.

Keep `tests/unification/native_contract.test.mjs` green.

## Shadow evaluation

`scripts/memory_unification_shadow.py` compares legacy vs unified over the pinned
cases from `scripts/memory_unification_eval.py` — same query, same context, one run
each, retrieval correctness and answer correctness recorded **separately**.
Private results only, under the control root
`/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification/shadow/<UTC Z>/`.
Record per case: query, backend status, ranked references, citations with revision,
p50/p95 from repeated runs with n, corpus/revision fingerprints, coverage, and the
**unique facts lost** by public-only exclusion (the point of the number, not a
formality). No credentials, no copyrighted corpus text, no GM-private evidence in
git. Small-corpus timings are experimental and must be labelled as such — they are
not full-wiki p95 claims. The U2 targets (<=2s campaign/equipment warm, <=4.5s
rules) are engineering targets; report measured values and say if unmet.
