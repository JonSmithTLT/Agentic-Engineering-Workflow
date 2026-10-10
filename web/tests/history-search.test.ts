import { afterEach, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { HistorySearchSession } from '../src/client/history-search';
import { ReadTransport } from '../src/api/transport';
import { installVisibility } from '../src/client/queries';
import { readOnlyHistoryArgv } from '../src/api/cli';
import f1 from '../src/api/mock/fixtures/F1.json';
import { HistorySearchResponse } from '../src/api/additive-schema';
import { historySearchEcho } from '../src/api/maps-history';

const clients: QueryClient[] = [];
it('accepts the served S2 fractional-bound echo without changing the submitted terms', async () => {
  const { session } = setup();
  await session.submit({ terms: ['fictional'], since: '2026-10-02T11:59:59.000001Z', until: '2026-10-02T12:00:00.999Z' });
  expect(session.snapshot().error).toBeUndefined();
  expect(session.snapshot().result?.value.data.query).toMatchObject({
    terms: ['fictional'], since: '2026-10-02T12:00:00Z', until: '2026-10-02T12:00:00Z',
  });
  expect(historySearchEcho({ terms: ['fictional'], since: '2026-10-02T12:00:00.000Z' }).since).toBe('2026-10-02T12:00:00Z');
});
afterEach(() => clients.splice(0).forEach(client => client.clear()));
function setup() {
  const calls: { url: string; validator: string | null }[] = [];
  let response: number | 'mismatch' | 'hold' = 200;
  let release: (() => void) | undefined;
  const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    calls.push({ url: url.href, validator: new Headers(init?.headers).get('If-None-Match') });
    const status = response;
    if (status === 'hold') await new Promise<void>(resolve => { release = resolve; });
    if (typeof status === 'number' && status !== 200)
      return new Response(null, { status, headers: { ETag: '"search"' } });
    const value = structuredClone(f1.responses['/history/search']);
    value.data.query = historySearchEcho({
      terms: status === 'mismatch' ? ['wrong query'] : url.searchParams.getAll('term'),
      kinds: url.searchParams.getAll('kind'), since: url.searchParams.get('since') ?? undefined,
      until: url.searchParams.get('until') ?? undefined, limit: Number(url.searchParams.get('limit') ?? 10),
    }) as typeof value.data.query;
    return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json', ETag: '"search"' } });
  });
  const reader = new ReadTransport(request);
  reader.context.bind('aew-demo');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  const session = new HistorySearchSession(reader, client);
  session.bind(true);
  return { session, reader, client, calls, request, setResponse: (next: typeof response) => { response = next; }, release: () => release?.() };
}
const query = { terms: ['fictional clangd'], kinds: [], limit: 10 };
it('does not search on binding, edits, foreground callbacks, or cache refresh coordination', async () => {
  const { session, calls, client } = setup();
  session.edit({ ...session.snapshot().draft, terms: ['fictional'] });
  const dispose = installVisibility(client);
  window.dispatchEvent(new Event('focus'));
  document.dispatchEvent(new Event('visibilitychange'));
  expect(calls).toHaveLength(0);
  await session.submit(query);
  window.dispatchEvent(new Event('focus'));
  await client.refetchQueries({ type: 'active' });
  expect(calls).toHaveLength(1);
  expect(client.getQueryCache().getAll()[0].meta?.automaticRevalidation).toBe(false);
  dispose();
});
it('retains represented payload and generation time on explicit conditional replay', async () => {
  const { session, calls, setResponse } = setup();
  await session.submit(query);
  const first = session.snapshot().result;
  setResponse(304);
  await session.submit(query);
  expect(calls[1].validator).toBe('"search"');
  expect(session.snapshot().result?.value).toBe(first?.value);
  expect(session.snapshot().result?.value.generated_at).toBe(first?.value.generated_at);
});
it('keeps valid data on ordinary refresh failure but clears data and validators on refusal', async () => {
  const { session, setResponse, calls } = setup();
  await session.submit(query);
  const first = session.snapshot().result;
  setResponse(500); await session.submit(query);
  expect(session.snapshot().result).toBe(first);
  expect(session.snapshot().error).toContain('500');
  setResponse(403); await session.submit(query);
  expect(session.snapshot().result).toBeUndefined();
  setResponse(200); await session.submit(query);
  expect(calls.at(-1)?.validator).toBeNull();
});
it('Clear retires held results, removes cached payloads/validators and makes no replacement request', async () => {
  const { session, setResponse, release, calls, client } = setup();
  setResponse('hold');
  const pending = session.submit(query);
  expect(session.snapshot().pending).toBe(true);
  await vi.waitFor(() => expect(calls).toHaveLength(1));
  session.clear(); release(); await pending;
  expect(session.snapshot().submitted).toBeUndefined();
  expect(session.snapshot().result).toBeUndefined();
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  expect(calls).toHaveLength(1);
  setResponse(200); await session.submit(query);
  expect(calls[1].validator).toBeNull();
});
it('does not allow duplicate pending submission or a late answer after capability loss', async () => {
  const { session, setResponse, release, calls } = setup();
  setResponse('hold'); const first = session.submit(query);
  await session.submit({ terms: ['other'] });
  await vi.waitFor(() => expect(calls).toHaveLength(1));
  expect(calls).toHaveLength(1);
  session.bind(false); release(); await first;
  expect(session.snapshot().result).toBeUndefined();
  await session.submit(query);
  expect(calls).toHaveLength(1);
});
it('replaces query identity without retaining the preceding result or an unbound response', async () => {
  const { session, setResponse, calls, client } = setup();
  await session.submit(query);
  setResponse('mismatch'); await session.submit({ terms: ['other query'], kinds: ['unit'], limit: 25 });
  expect(session.snapshot().result).toBeUndefined();
  expect(session.snapshot().error).toContain('different submitted query');
  expect(client.getQueryCache().getAll()).toHaveLength(1);
  setResponse(200); await session.submit({ terms: ['other query'], kinds: ['unit'], limit: 25 });
  expect(calls.at(-1)?.validator).toBeNull();
});
it('suspends a pending navigation without losing valid in-memory Back results', async () => {
  const { session, setResponse, release, calls } = setup();
  await session.submit(query);
  const first = session.snapshot().result;
  setResponse('hold'); const pending = session.submit(query);
  await vi.waitFor(() => expect(calls).toHaveLength(2));
  session.suspend(); release(); await pending;
  expect(session.snapshot().result).toBe(first);
  expect(session.snapshot().pending).toBe(false);
  expect(calls).toHaveLength(2);
});
it('clears the memory session on project/session retirement', async () => {
  const { session, reader, client } = setup();
  await session.submit(query);
  reader.reset(); client.clear(); session.bind(false);
  expect(session.snapshot().draft.terms).toEqual(['']);
  expect(session.snapshot().result).toBeUndefined();
});
it('fixtures use accepted bounded shapes and copy only allowlisted read-only argv', () => {
  expect(HistorySearchResponse.safeParse(f1.responses['/history/search']).success).toBe(true);
  expect(readOnlyHistoryArgv(['aew', 'history', 'show', 'T-0004'])).toBe('aew history show T-0004');
  for (const argv of [['rm', '-rf', '/'], ['aew', 'history', 'show', '--help'], ['aew', 'history', 'show', 'T-0004; whoami'], ['aew', 'history', 'show', 'T-0004', '--json']])
    expect(readOnlyHistoryArgv(argv)).toBeUndefined();
});
