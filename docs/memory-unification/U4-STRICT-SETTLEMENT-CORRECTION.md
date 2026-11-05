# Packet41 — strict settlement report correction

Corrects the acceptance-blocking Packet40 finding in the default-off synthetic
fixture only. Both `settle` and `reconcile` now require `resourcesSettled === true`.
Malformed/missing/false values cannot release custody: settle quarantines resources;
reconcile denies while keeping the existing quarantine. No value coercion is used.
This does not authenticate report origin or prove native resource settlement.

## Validation

- Two new regression groups against the original fixture: **0 pass / 2 intended
  assertion failures**, exit 1, both `NON_BOOLEAN_SETTLEMENT_MUST_RETAIN_FENCES`.
- Final exact-source suite: **34/34 pass**, exit 0. Includes all prior 30 tests,
  two settlement-value regression groups and two narrow truthiness mutant controls.
- Each value group checks 15 values: false, undefined, null, zero, NaN, empty/string
  values, positive/negative numbers, object, array, boxed boolean, function and poison
  proxy. Value objects are not inspected/coerced. Both owner fences, transaction,
  quarantine, attempt and ingress remain held; later literal true settles once.
- Two new narrow mutants separately restore truthiness in settle/reconcile. Both
  string and object reports fail the intended custody assertion in each mutant.
  With six inherited mutants, eight broken variants are discriminated, not accepted.
- Fixture and validator hashes bound before/after the final run; final bytes saved.
  Experimental VM Modules warning retained. VM is not a security sandbox.
- Parent reverified 379 Packet40 closure bindings, using six exact beforeimages
  where needed; Packet40's four original failed adversarial probes remain intact.

Same-owner correction validation only; independent review of these new bytes is
still pending. Packet40's rejection remains the historical verdict for Packet39.
No host compiler/declaration/build, old suite, real reader/provider/session/DB/worker,
network or live retrieval executed. Literal remains false; no host installation,
restart, deployment, config, routing, voice, rights, promotion or U5 change.
Both real lanes unavailable. Native owner participation, admitted authority,
loaded/dependency/build identity, compatible confinement, whole resource settlement,
production-write denial and declaration acceptance remain open. No native atomicity,
crash recovery, physical nonmutation, quality/loss/parity/latency or global clearance.
All source-review and claim counts/statuses unchanged. HEARTBEAT/notifier outside
scope, not newly attested unchanged. Next: independent exact-source correction review.
