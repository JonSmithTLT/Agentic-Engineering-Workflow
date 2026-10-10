import { z } from 'zod';
import { ObjectId, Sha256, Timestamp } from './additive-schema';
const sections = ['directories', 'languages', 'build_descriptors', 'entry_point_candidates', 'test_candidates', 'generated_and_vendor', 'semantic_prerequisites', 'limits_and_omissions'] as const;
const page = (maximum: number) => z.number().int().min(1).max(maximum);
const mapQuery = z.strictObject({ against: ObjectId.optional() });
const listQuery = z.strictObject({ source_revision: ObjectId.optional(), cursor: z.string().min(1).optional(), limit: page(50).optional() });
const detailQuery = mapQuery.extend({ section: z.enum(sections).optional() });
const inputsQuery = z.strictObject({ cursor: z.string().min(1).optional(), limit: page(250).optional() });
const searchQuery = z.strictObject({
  terms: z.array(z.string().min(1)).min(1).max(16),
  kinds: z.array(z.string().min(1)).max(16).default([]),
  since: Timestamp.optional(), until: Timestamp.optional(), limit: page(50).default(10),
}).refine(value => value.terms.reduce((sum, term) => sum + Array.from(term).length, 0) <= 512, 'Terms exceed 512 characters')
  .refine(value => !value.since || !value.until || Date.parse(value.since) <= Date.parse(value.until), 'Date range is reversed');
export type SubmittedHistorySearch = z.input<typeof searchQuery>;
function route(path: string, values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined) params.set(key, String(value));
  return path + (params.size ? `?${params}` : '');
}
export const mapsRoute = (query: z.input<typeof mapQuery> = {}) => route('/maps', mapQuery.parse(query));
export const storedMapsRoute = (query: z.input<typeof listQuery> = {}) => route('/maps/structural', listQuery.parse(query));
export const structuralMapRoute = (root: string, query: z.input<typeof detailQuery> = {}) => route(`/maps/structural/${Sha256.parse(root)}`, detailQuery.parse(query));
export const mapInputsRoute = (root: string, query: z.input<typeof inputsQuery> = {}) => route(`/maps/structural/${Sha256.parse(root)}/inputs`, inputsQuery.parse(query));
export const mapDiffRoute = (a: string, b: string) => route('/maps/diff', { a: Sha256.parse(a), b: Sha256.parse(b) });
// Pure builder: search execution belongs solely to an explicit submitted action.
export function historySearchRoute(input: SubmittedHistorySearch) {
  const query = searchQuery.parse(input);
  const params = new URLSearchParams();
  for (const term of query.terms) params.append('term', term);
  for (const kind of query.kinds) params.append('kind', kind);
  if (query.since) params.set('since', query.since);
  if (query.until) params.set('until', query.until);
  params.set('limit', String(query.limit));
  if (new TextEncoder().encode(params.toString()).length > 2048) throw new Error('Encoded search query exceeds 2 KiB');
  return `/history/search?${params}`;
}
