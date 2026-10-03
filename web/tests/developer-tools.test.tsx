import { expect, it, vi } from 'vitest';
import { ReadTransport } from '../src/api/transport';
import { RequestLog } from '../src/api/diagnostics';
import { readOnlyCommand } from '../src/api/cli';
import { responseSchemas, historyDetail } from '../src/api/schema';
import {
  readView,
  rememberView,
  compareView,
  type SavedView,
} from '../src/client/view-memory';
import f1 from '../src/api/mock/fixtures/F1.json';
const normal = f1.responses['/project'];
it('diagnostics retains 200 and 304 validators/revision while preserving representation generation time', async () => {
  const log = new RequestLog(2);
  const request = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json(normal, { headers: { ETag: '"one"' } }),
    )
    .mockResolvedValueOnce(
      new Response(null, { status: 304, headers: { ETag: '"one"' } }),
    );
  const client = new ReadTransport(
    request,
    () => new Date('2026-10-02T14:00:00Z'),
    log,
  );
  const first = await client.get('/project', responseSchemas.ProjectResponse),
    second = await client.get('/project', responseSchemas.ProjectResponse);
  expect(second.value).toBe(first.value);
  expect(second.value.generated_at).toBe(normal.generated_at);
  expect(log.snapshot().map((t) => t.status)).toEqual([304, 200]);
  expect(log.snapshot()[0]).toMatchObject({
    request_etag: '"one"',
    response_etag: '"one"',
    represented_etag: '"one"',
    control_revision: '42',
  });
  expect(Object.keys(log.snapshot()[0])).not.toContain('body');
});
it('diagnostics shows exact invalid field, bounds its log and observes same-ETag revision changes without rejecting valid data', async () => {
  const log = new RequestLog(2),
    bad = structuredClone(normal) as unknown as { data: { name: unknown } };
  bad.data.name = 7;
  const next = { ...normal, control_revision: '43' };
  const request = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json(normal, { headers: { ETag: '"same"' } }),
    )
    .mockResolvedValueOnce(Response.json(bad))
    .mockResolvedValueOnce(
      Response.json(next, { headers: { ETag: '"same"' } }),
    );
  const client = new ReadTransport(request, undefined, log);
  await client.get('/project', responseSchemas.ProjectResponse);
  await expect(
    client.get('/project', responseSchemas.ProjectResponse),
  ).rejects.toThrow();
  expect(log.snapshot()[0].validation[0].field).toBe('data.name');
  const valid = await client.get('/project', responseSchemas.ProjectResponse);
  expect(valid.value.control_revision).toBe('43');
  expect(log.snapshot()).toHaveLength(2);
  expect(log.snapshot()[0].diagnostic).toContain('revision changed');
  log.clear();
  expect(log.snapshot()).toEqual([]);
});
it('network failure and uncached 304 remain failures recorded without changing the transport semantics', async () => {
  const log = new RequestLog(),
    request = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(new Response(null, { status: 304 }));
  const client = new ReadTransport(request, undefined, log);
  await expect(
    client.get('/project', responseSchemas.ProjectResponse),
  ).rejects.toThrow('offline');
  await expect(
    client.get('/project', responseSchemas.ProjectResponse),
  ).rejects.toThrow('304 without');
  expect(log.snapshot().map((t) => t.status)).toEqual([304, null]);
});
it('CLI copies only verified read-only commands and shell-safe opaque IDs; missing commands stay absent', () => {
  expect(readOnlyCommand('ticket', 'T-0042')).toBe('aew work show T-0042');
  expect(readOnlyCommand('invocation', 'opaque.run-1')).toBe(
    'aew invoke show opaque.run-1',
  );
  expect(readOnlyCommand('history', 'T-0042')).toBe('aew history show T-0042');
  for (const id of ['-flag', 'T;rm', '$(secret)', 'T\n42', "T'42"])
    expect(readOnlyCommand('work', id)).toBeUndefined();
  expect(
    readOnlyCommand('evidence', 'INV-0001-verification-1'),
  ).toBeUndefined();
});
it('view memory compares only one bounded project/page baseline, labels arrivals and preserves newer revisions', () => {
  window.localStorage.clear();
  const prior: SavedView = {
    project: 'p',
    scope: 'work:live',
    revision: '9007199254740993',
    at: '2026-10-02T12:00:00Z',
    items: [
      { id: 'A', state: 'RUNNING' },
      { id: 'Gone', state: 'READY' },
    ],
  };
  rememberView(window.localStorage, prior);
  const current = {
    ...prior,
    revision: '9007199254740994',
    items: [
      { id: 'A', state: 'DONE' },
      { id: 'B', state: 'READY' },
    ],
  };
  expect(compareView(prior, current).changes).toEqual([
    { id: 'A', from: 'RUNNING', to: 'DONE' },
    { id: 'B', from: undefined, to: 'READY' },
  ]);
  expect(readView(window.localStorage, 'p', 'work:demo')).toBeUndefined();
  expect(readView(window.localStorage, 'other', 'work:live')).toBeUndefined();
  rememberView(window.localStorage, current);
  rememberView(window.localStorage, prior);
  expect(readView(window.localStorage, 'p', 'work:live')?.revision).toBe(
    current.revision,
  );
  expect(compareView(current, prior).older).toBe(true);
  for (let n = 0; n < 25; n++)
    rememberView(window.localStorage, { ...prior, scope: 'page' + n });
  expect(readView(window.localStorage, 'p', 'page0')).toBeUndefined();
  expect(readView(window.localStorage, 'p', 'page24')).toBeDefined();
});
it('malformed storage starts empty and rejected storage operations remain catchable by the UI', () => {
  window.localStorage.setItem('aew-dashboard-view-memory-v1', 'not json');
  expect(readView(window.localStorage, 'p', 'view')).toBeUndefined();
  const blocked = {
    getItem() {
      throw new Error('blocked');
    },
  } as unknown as Storage;
  expect(() => readView(blocked, 'p', 'view')).toThrow('blocked');
});

it('historical graph bounds supplied references and does not automatically crawl them', async () => {
  const { render, screen, fireEvent, waitFor } =
    await import('@testing-library/react');
  const { QueryClient, QueryClientProvider } =
    await import('@tanstack/react-query');
  const { MemoryRouter } = await import('react-router-dom');
  const { DashboardProvider } = await import('../src/client/dashboard');
  const { LineageGraph } = await import('../src/components/LineageGraph');
  const { DemoProjector } = await import('../src/api/mock/projector');
  const server = new DemoProjector(f1);
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async (input) => {
      const result = server.read(new URL(String(input), 'http://localhost'));
      return Response.json(result.body, { status: result.status });
    });
  const record = historyDetail.parse(
    structuredClone(f1.responses['/history/T-0004'].data),
  );
  record.links = {
    depends_on: Array.from({ length: 100 }, (_, i) => 'T-L' + i),
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const rendered = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardProvider>
          <LineageGraph record={record} />
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const expand = await screen.findByRole('button', {
    name: 'Expand links',
  });
  await waitFor(() =>
    expect((expand as HTMLButtonElement).disabled).toBe(false),
  );
  fireEvent.click(expand);
  await screen.findByText(/Graph limit reached/);
  expect(rendered.container.querySelectorAll('.lineage-card')).toHaveLength(24);
  expect(
    fetcher.mock.calls.some(([url]) => String(url).includes('/history/')),
  ).toBe(false);
  rendered.unmount();
  client.clear();
});
