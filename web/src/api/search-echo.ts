/** Accepted S2 projector echo at whole-second history precision, not a search executor. */
export function searchEcho(query: { terms: string[]; kinds?: string[]; since?: string; until?: string; limit?: number }) {
  function bound(value: string | undefined, lower: boolean) {
    if (!value) return null;
    const fraction = value.match(/\.(\d+)Z$/)?.[1];
    const whole = value.replace(/\.\d+Z$/, 'Z');
    return lower && fraction && /[1-9]/.test(fraction)
      ? new Date(Date.parse(whole) + 1000).toISOString().replace('.000Z', 'Z') : whole;
  }
  return { terms: query.terms, kinds: [...new Set(query.kinds ?? [])].sort(),
    since: bound(query.since, true), until: bound(query.until, false), limit: query.limit ?? 10 };
}
