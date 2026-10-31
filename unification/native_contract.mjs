/** Boundary normalization for a borrowed private-local native provider.
 * This does not mint authority, authorize sources, or turn scores into confidence.
 * Source eligibility/revocation remains the partition/host owner's responsibility.
 */
export function enforceMinimumScore(page, minScore) {
  if (minScore === undefined) return page;
  if (typeof minScore !== 'number' || !Number.isFinite(minScore) || minScore < 0) {
    throw new Error('finite nonnegative minimum score required');
  }
  // Installed native hybrid retrieval admits lexical fallback below minScore.
  // Provider-neutral consumers require a strict final filter, including when a
  // backend omits scores or supplies NaN. Never compare scores across backends.
  return {...page,hits:page.hits.filter(hit => typeof hit.score === 'number' &&
    Number.isFinite(hit.score) && hit.score >= minScore)};
}
