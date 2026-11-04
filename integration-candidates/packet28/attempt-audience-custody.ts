/** Host-private PATCH CANDIDATE ONLY. No provider access or authority minting.
 * The resolver owns the release/no-op decision; never infer it from wire fields.
 * This closes local setup cleanup coverage, NOT worker settlement or effect fences.
 */
export async function withAttemptAudienceCustody<T>(
  releaseAudience: () => void,
  clearAbort: () => void,
  operation: (ownControls: (controls: { close: () => void }) => void) => Promise<T>,
): Promise<T> {
  let controls: { close: () => void } | undefined;
  try {
    return await operation((value) => {
      if (controls) throw new Error("Attempt controls already registered");
      controls = value;
    });
  } finally {
    try {
      controls?.close();
    } finally {
      try {
        releaseAudience();
      } finally {
        clearAbort();
      }
    }
  }
}
