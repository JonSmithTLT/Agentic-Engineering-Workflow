/** Presentation equality only. These utilities never assign semantic relationships. */
export function structuralState(a: unknown, b: unknown, complete = true) {
  if (!complete || a === null || a === undefined || b === null || b === undefined) return 'Unavailable';
  return JSON.stringify(a) === JSON.stringify(b) ? 'Same supplied value' : 'Different supplied values';
}
export function referenceIdentities(values: { kind: string; id: string }[]) {
  return [...new Set(values.map(v => JSON.stringify([v.kind, v.id])))].sort();
}
