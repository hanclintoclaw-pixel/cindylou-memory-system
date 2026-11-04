# U4 — fixed synthetic platform confinement (packet23)

This is a bounded engineering proof, **not reader-execution clearance**.
`unification/confinement.py` and the explicit opt-in CLI accept only a scratch
parent, never arbitrary commands, reader adapters or protected production paths.
Default-off and all non-synthetic lanes return unavailable before touching inputs
or launching a process. Unsupported platforms/missing or failed controls remain
unavailable; no unsandboxed fallback exists.

## Implemented and exercised

On the current Darwin host, the installed `sandbox-exec` applies a Seatbelt profile
to a fixed isolated-mode Python payload. All protected targets are fresh synthetic
fixtures. Writes are allowed only beneath the new writable scratch directory;
file links, network operations and process-fork are denied. Default reads and
other system/IPC operations are **not** restricted by this profile.

The actual child proved an allowed scratch write, and eleven adversarial controls
returned EPERM: protected overwrite, create, unlink, rename, replace, chmod,
write through a symlink, hardlink creation, a synthetic SQLite-sidecar creation,
fork and detached subprocess spawn. Protected sentinel bytes, size, mtime, mode,
inode and directory membership were unchanged. No real SQLite database was opened.
A second fixed child signaled startup, exceeded its deadline, received SIGKILL
and was reaped before the final protected-fixture check.

This uses **kernel prevention of descendant creation**, not post-hoc supervision
of arbitrary forked/detached grandchildren. A separate process group is cleanup
defense-in-depth, not escape-proof descendant tracking. The native stack's real
workers cannot run under this fork-denying profile; enabling them would require a
separate bounded inheritance, tracking and settlement proof first.

The receipt retains profile/payload/interpreter/sandbox-binary hashes, exact
control results, protected identities, process completion and failure limitations.
All real platform proof artifacts remain in private runtime storage. Initial
successful controls were retained separately from final code-pinned controls.

## Verification actually run

- Twelve targeted tests passed, including actual kernel controls plus rejection
  of real lanes, unsupported platform, missing launcher, failed sandbox launch,
  healthy exit without proof, malformed result, modified protected fixture,
  un-settled timeout and unsafe/symlink scratch parents.
- Actual CLI default-off returned unavailable; opt-in CLI passed the fixed
  synthetic proof. Source hashes/sizes/mtimes were frozen before these final tests
  and controls and freshly compared afterward (three new Python files).
- Nineteen prepared private CP18/CP19 cases/two origin groups were consumed only
  for data/status/source-hash preservation; both real lanes remain unavailable.
  All 45 prior native source bindings and three prior harness code bindings
  matched. These are source identities, not compiled-provider equivalence.
- Selected production/source/caller/config/two-section pilot/API process/socket
  and 346 prior artifact paths were preserved; RESUME only appends old bytes.
  Historical broader runtime inventory receipts remain retained, not rerun.

## Still unproven

Synthetic targets do not establish production write-denial, a complete transitive
sandbox, confidentiality, system/IPC or network isolation, native worker
containment, current host-issued revocable authority or compiled provider/worker
identity. No reader/provider/model/HTTP/tool execution, real retrieval/get,
paired answers, answer quality, loss, public parity or service latency was tested.
No full Python/Node suites, import/reimport, rebuild, restart, deploy, rights
expansion, promotion, primary-reader/routing/config/voice change or U5 occurred.
Parent-owned HEARTBEAT/notifier were neither edited nor attested unchanged.

Counts remain 301/301 sources read, zero unread, 184 mixed/unresolved tasks,
1206 findings, zero promoted, unique claims unassessed and 32 partial/mixed
summaries. Prior failures/originals/quarantine remain. Stop after this packet for
independent parent review. The next bounded preparation should resolve actual
host authority and emitted-provider/worker identity feasibility from code without
running readers; real execution and fork-compatible confinement remain gated.
The old conditional 18–30 active-hour estimate is historical, not a new ETA.
