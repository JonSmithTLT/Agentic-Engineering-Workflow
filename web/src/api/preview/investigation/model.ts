/** Presentation equality only. These utilities never assign semantic relationships. */
export function structuralState(a: unknown, b: unknown, complete = true) {
  if (!complete || a === null || a === undefined || b === null || b === undefined) return 'Unavailable';
  return canonical(a) === canonical(b) ? 'Same supplied value' : 'Different supplied values';
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return JSON.stringify(value.map(canonical).sort());
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    if (typeof record.id === 'string' && typeof record.kind === 'string') return JSON.stringify([record.kind, record.id]);
    if (typeof record.format === 'string' && typeof record.text === 'string') return JSON.stringify(record.text);
    return JSON.stringify(Object.keys(record).sort().map(key => [key, canonical(record[key])]));
  }
  return JSON.stringify(value) ?? 'undefined';
}
export function referenceIdentities(values: { kind: string; id: string }[]) {
  return [...new Set(values.map(v => JSON.stringify([v.kind, v.id])))].sort();
}
