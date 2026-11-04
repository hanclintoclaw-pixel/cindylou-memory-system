/** Uninstalled, host-private lifetime pairing candidate. NOT a read grant.
 * The only production policy is disabled; no provider, IPC or worker import.
 * Minting is internal to this dispatch wrapper, never from wire identifiers.
 */
import { resolveAdmittedRunActiveAssertion, type AdmittedRunContext } from "../../admitted-run-context.js";
import { assertMemoryAudienceCurrent, isHostMemoryAudience } from "../../../plugins/memory-audience.js";
import type { MemoryAudience } from "../../../plugins/memory-provider-types.js";
import { withAttemptAudienceCustody } from "./attempt-audience-custody.js";

const ATTEMPT_MEMORY_BINDING_ENABLED = false;
export type AttemptMemoryBinding = Readonly<{ kind: "attempt-memory-binding" }>;
type BindingRecord = {
  admitted: AdmittedRunContext;
  audience: MemoryAudience;
  assertCurrent: () => void;
};
const bindings = new WeakMap<AttemptMemoryBinding, BindingRecord>();

/** Identity AND active lifetime are required; separate valid objects are not a pair.
 * Success proves only this module's local pairing, not effect/worker authority.
 */
export function assertAttemptMemoryBinding(
  binding: AttemptMemoryBinding,
  admitted: AdmittedRunContext,
  audience: MemoryAudience,
): void {
  const record = bindings.get(binding);
  if (!record || record.admitted !== admitted || record.audience !== audience) {
    throw new Error("attempt memory binding unavailable");
  }
  try {
    record.assertCurrent();
  } catch (error) {
    bindings.delete(binding);
    throw error;
  }
}

/** Called at the resolver-returned audience/original admitted-context handoff.
 * The resolver's release/no-op remains the sole lease owner. Binding deletion
 * happens before controls close and audience release, including setup failures.
 * Disabled operation does not inspect the captured pair or perform assertions.
 * The handle is NOT yet forwarded to a backend/executor; no read gate is cleared.
 */
export async function withBoundAttemptAudienceCustody<T>(
  releaseAudience: () => void,
  clearAbort: () => void,
  admitted: AdmittedRunContext,
  audience: MemoryAudience | undefined,
  operation: (
    ownControls: (controls: { close: () => void }) => void,
    binding: AttemptMemoryBinding | undefined,
  ) => Promise<T>,
): Promise<T> {
  return withAttemptAudienceCustody(releaseAudience, clearAbort, async (ownControls) => {
    if (!ATTEMPT_MEMORY_BINDING_ENABLED) return operation(ownControls, undefined);
    if (!audience || !isHostMemoryAudience(audience)) {
      throw new Error("attempt memory binding unavailable");
    }
    const assertAdmitted = resolveAdmittedRunActiveAssertion(admitted);
    if (!assertAdmitted) throw new Error("attempt memory binding unavailable");
    const assertCurrent = () => {
      assertAdmitted();
      assertMemoryAudienceCurrent(audience);
    };
    assertCurrent();
    const binding = Object.freeze({ kind: "attempt-memory-binding" } as const);
    bindings.set(binding, { admitted, audience, assertCurrent });
    try {
      return await operation(ownControls, binding);
    } finally {
      bindings.delete(binding);
    }
  });
}
