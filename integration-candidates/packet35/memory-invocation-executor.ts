/** Uninstalled host-private candidate. Admission custody only, NOT a read capability.
 * No runtime/provider import, IPC, worker, effect, source lookup or lease ownership.
 * The immutable disabled policy has no environment/config/public enable switch.
 */
import {
  resolveAdmittedRunActiveAssertion,
  type AdmittedRunContext,
} from "../agents/admitted-run-context.js";
import { assertMemoryCallerCurrent, isHostMemoryAudience } from "./memory-audience.js";
import type { MemoryCallerContext } from "./memory-provider-types.js";

import { assertAttemptMemoryBinding, type AttemptMemoryBinding } from "../agents/embedded-agent-runner/run/attempt-memory-binding.js";

const INVOCATION_MEMORY_EXECUTOR_ENABLED = false;

export type InvocationMemoryExecutor = Readonly<{ kind: "memory-invocation-executor" }>;
type Capture = Readonly<{
  admittedRunContext: AdmittedRunContext;
  callerContext: MemoryCallerContext;
  binding: AttemptMemoryBinding;
  signal: AbortSignal;
}>;
type Record = { assertCurrent: () => void; closed: boolean };
const records = new WeakMap<InvocationMemoryExecutor, Record>();
const unavailable = () =>
  Object.freeze({ status: "unavailable", reason: "integration_prerequisites_missing" } as const);

/** Retains the exact host-supplied objects; never reconstructs admission from IDs.
 * Prepared means local custody only. No existing API binds all admission, identity,
 * atomic-effect, confinement and settlement proofs; therefore dispatch cannot read.
 * The attempt's existing finally retains sole release custody of its audience.
 */
export function createInvocationMemoryExecutor(params: {
  optIn: boolean;
  capture: () => Capture;
}):
  | { status: "unavailable"; reason: "disabled" | "opt_in_required" | "authority_unavailable" }
  | { status: "prepared"; executor: InvocationMemoryExecutor } {
  // Disabled must not evaluate any caller property, factory or authority lookup.
  if (!INVOCATION_MEMORY_EXECUTOR_ENABLED) return { status: "unavailable", reason: "disabled" };
  if (params.optIn !== true) return { status: "unavailable", reason: "opt_in_required" };
  try {
    const { admittedRunContext, callerContext, binding, signal: attemptSignal } = params.capture();
    if (callerContext.signal !== attemptSignal) return { status: "unavailable", reason: "authority_unavailable" };
    const authority = callerContext.authority;
    if (authority.kind !== "session" || !isHostMemoryAudience(authority.audience)) {
      return { status: "unavailable", reason: "authority_unavailable" };
    }
    const audience = authority.audience;
    const sessionKey = authority.sessionKey;
    const sessionId = authority.sessionId;
    const sandboxed = authority.sandboxed;
    const audienceAgentId = audience.agentId;
    const signal = callerContext.signal;
    const assertCaller = callerContext.assertCurrent;
    const assertAdmitted = resolveAdmittedRunActiveAssertion(admittedRunContext, signal);
    if (!assertAdmitted) return { status: "unavailable", reason: "authority_unavailable" };
    const assertCurrent = () => {
      if (
        callerContext.authority !== authority || authority.kind !== "session" || authority.audience !== audience ||
        authority.sessionKey !== sessionKey || authority.sessionId !== sessionId ||
        authority.sandboxed !== sandboxed || audience.agentId !== audienceAgentId ||
        callerContext.signal !== signal || callerContext.assertCurrent !== assertCaller
      ) throw new Error("invocation custody changed");
      assertAttemptMemoryBinding(binding, admittedRunContext, audience, callerContext, attemptSignal);
      assertAdmitted();
      assertMemoryCallerCurrent(callerContext);
    };
    assertCurrent();
    const executor = Object.freeze({ kind: "memory-invocation-executor" } as const);
    records.set(executor, { assertCurrent, closed: false });
    return { status: "prepared", executor };
  } catch {
    // No error payload, IDs, paths or source contents escape this boundary.
    return { status: "unavailable", reason: "authority_unavailable" };
  }
}

/** No request fields are inspected before the missing prerequisites deny access.
 * Currency checks do NOT supply an atomic effect fence or admission/session binding.
 * There is intentionally no provider acquisition path, including synthetic fallback.
 */
export function dispatchInvocationRead(executor: InvocationMemoryExecutor, _request: unknown) {
  const record = records.get(executor);
  if (!record || record.closed) return { status: "denied", reason: "invalid_executor" } as const;
  try {
    record.assertCurrent();
  } catch {
    record.closed = true;
    return { status: "denied", reason: "authority_unavailable" } as const;
  }
  return unavailable();
}

export function revokeInvocationExecutor(executor: InvocationMemoryExecutor): void {
  const record = records.get(executor);
  if (record) record.closed = true;
}

/** No resources are allocated by this scaffold. Not a worker settlement receipt. */
export function settleInvocationExecutor(executor: InvocationMemoryExecutor): void {
  revokeInvocationExecutor(executor);
  records.delete(executor);
}
