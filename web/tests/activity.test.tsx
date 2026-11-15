import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { DashboardProvider } from '../src/client/dashboard';
import { ActivityPage } from '../src/pages/Activity';
import { DemoProjector } from '../src/api/mock/projector';
import type { World } from '../src/api/mock/types';
import f1 from '../src/api/mock/fixtures/F1.json';
import f7 from '../src/api/mock/fixtures/F7.json';
import { setReadClock } from '../src/client/clock';
import { installVisibility } from '../src/client/queries';

function mount({ denied = false, empty = false, search = '', keepCache = false, recordCount = 61 } = {}) {
  const world = structuredClone(f1) as World;
  const envelope = world.responses['/activity'] as { data: { items: unknown[] } };
  envelope.data.items = empty ? [] : Array.from({ length: recordCount }, (_, index) => ({
    id: `R${recordCount - index}`, occurred_at: '2026-10-12T12:00:00.123456Z',
    title: `Supplied activity ${recordCount - index}`,
    subject: index === 0 ? { id: 'T-0001', kind: 'work', title: 'Supplied ticket' } : { id: `S${index}`, kind: 'transition', title: index === 3 ? '' : 'Supplied transition' },
    reason: index === 0 ? { code: 'SUPPLIED_REASON', message: '<script>hostile()</script>' } : null,
  }));
  if (denied) (world.responses['/capabilities'] as { data: Record<string, unknown> }).data.activity = { state: 'UNSUPPORTED', reasons: [{ code: 'NOT_ENABLED', message: 'Activity unavailable.' }] };
  const server = new DemoProjector(world);
  const request = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const result = server.read(new URL(String(input), 'http://localhost'));
    return new Response(JSON.stringify(result.body), { status: result.status, headers: { 'Content-Type': 'application/json' } });
  });
  setReadClock({ manual: true, now: () => new Date('2026-10-12T12:00:00Z'), monotonic: () => 0, visible: () => true, subscribe: () => () => {} });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: keepCache ? Infinity : 0 } } });
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/activity' + search]}><DashboardProvider>
    <Routes>
      <Route path="/activity" element={<><Link to="/">Overview</Link><ActivityPage /></>} />
      <Route path="/" element={<Link to="/activity">View all activity</Link>} />
    </Routes>
  </DashboardProvider></MemoryRouter></QueryClientProvider>);
  return { request, client, view };
}

it('uses 50-record pages, preserves supplied order and replaces rows when paging', async () => {
  const { request } = mount();
  await screen.findByText('Supplied activity 61');
  expect(screen.getAllByTestId('activity-record')).toHaveLength(50);
  expect(request.mock.calls.some(([url]) => String(url).endsWith('/activity?limit=50'))).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  await screen.findByText('Supplied activity 11');
  expect(screen.queryByText('Supplied activity 61')).toBeNull();
  expect(screen.getAllByTestId('activity-record')).toHaveLength(11);
  expect(document.activeElement?.textContent).toBe('Activity records');
  fireEvent.click(screen.getByRole('button', { name: 'First page' }));
  await screen.findByText('Supplied activity 61');
});

it('returns through uncached pages in order', async () => {
  mount({ recordCount: 111 });
  await screen.findByText('Supplied activity 111');
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  await screen.findByText('Supplied activity 61');
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  await screen.findByText('Supplied activity 11');

  fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
  await screen.findByText('Supplied activity 61');
  expect(screen.queryByText('Supplied activity 111')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
  await screen.findByText('Supplied activity 111');
  expect(screen.getByRole('button', { name: 'Previous page' })).toHaveProperty('disabled', true);
});

it('fetches latest when paging or navigating back to a cached first page', async () => {
  const { request, client, view } = mount({ keepCache: true });
  try {
    await screen.findByText('Supplied activity 61');
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await screen.findByText('Supplied activity 11');
    const original = request.getMockImplementation()!;
    let newest = 62;
    request.mockImplementation(async (input, init) => {
      const response = await original(input, init);
      if (!String(input).endsWith('/activity?limit=50')) return response;
      const payload = await response.json();
      const items = payload.data.items;
      payload.data.items = [{ ...items[0], id: `R${newest}`, title: `New activity ${newest}` }, ...items.slice(0, 49)];
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    fireEvent.click(screen.getByRole('button', { name: 'First page' }));
    await screen.findByText('New activity 62');
    expect(request.mock.calls.filter(([url]) => String(url).endsWith('/activity?limit=50'))).toHaveLength(2);
    expect(screen.getAllByTestId('activity-record')).toHaveLength(50);
    fireEvent.click(screen.getByRole('link', { name: 'Overview' }));
    newest = 63;
    fireEvent.click(screen.getByRole('link', { name: 'View all activity' }));
    await screen.findByText('New activity 63');
    expect(request.mock.calls.filter(([url]) => String(url).endsWith('/activity?limit=50'))).toHaveLength(3);
  } finally {
    view.unmount();
    client.clear();
  }
});

it('shows full UTC timestamps, supplied reasons, safe text and explicit unavailable destinations', async () => {
  const { view } = mount();
  await screen.findByText('Supplied activity 61');
  expect(screen.getByRole('link', { name: 'Supplied ticket' }).getAttribute('href')).toBe('/work/T-0001');
  expect(screen.getAllByText('No detail view available.').length).toBeGreaterThan(0);
  for (const row of screen.getAllByRole('article', { name: /^Activity / })) expect(within(row).getByText('2026-10-12T12:00:00.123456Z')).toBeTruthy();
  expect(within(screen.getByRole('article', { name: 'Activity R60' })).getByText('S1')).toBeTruthy();
  expect(within(screen.getByRole('article', { name: 'Activity R59' })).getByText('S2')).toBeTruthy();
  expect(within(screen.getByRole('article', { name: 'Activity R58' })).getByText('S3')).toBeTruthy();
  expect(screen.getByText('<script>hostile()</script>')).toBeTruthy();
  expect(view.container.querySelector('script')).toBeNull();
  expect(screen.getAllByText('No reason supplied.').length).toBe(49);
});

it('keeps empty activity distinct from unavailable activity', async () => {
  mount({ empty: true });
  await screen.findByText('No records in this scope.');
});

it('does not read activity when its capability is unavailable', async () => {
  const { request } = mount({ denied: true });
  await screen.findAllByText('NOT_ENABLED: Activity unavailable.');
  expect(request.mock.calls.filter(([url]) => String(url).includes('/activity?'))).toHaveLength(0);
});

it('rejects unsupported duplicate cursors before any activity read', async () => {
  const { request } = mount({ search: '?cursor=a&cursor=b' });
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('No request was sent'));
  expect(request.mock.calls.filter(([url]) => String(url).includes('/activity?'))).toHaveLength(0);
});

it('retains visibly stale data on refresh failure, then removes it on refusal', async () => {
  const { request } = mount();
  await screen.findByText('Supplied activity 61');
  const normal = request.getMockImplementation()!;
  let status = 500;
  request.mockImplementation(async input => String(input).includes('/activity?') ? new Response('{}', { status, headers: { 'Content-Type': 'application/json' } }) : normal(input));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh page' }));
  await screen.findByText('STALE / DISCONNECTED');
  expect(screen.getAllByTestId('activity-record')).toHaveLength(50);
  status = 403;
  fireEvent.click(screen.getByRole('button', { name: 'Refresh page' }));
  await waitFor(() => expect(screen.queryByText('Supplied activity 61')).toBeNull());
});

it('makes no Activity interval or foreground reads while manual refresh still works', async () => {
  const { request, client, view } = mount();
  await screen.findByText('Supplied activity 61');
  const count = () => request.mock.calls.filter(([url]) => String(url).includes('/activity?')).length;
  const before = count();
  vi.useFakeTimers();
  setReadClock({ manual: false, now: () => new Date('2026-10-12T12:00:00Z'), monotonic: () => 0, visible: () => true, subscribe: () => () => {} });
  const dispose = installVisibility(client);
  await act(async () => { window.dispatchEvent(new Event('focus')); await vi.advanceTimersByTimeAsync(30000); });
  expect(count()).toBe(before);
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Refresh page' })));
  expect(count()).toBe(before + 1);
  dispose(); view.unmount(); client.clear();
});

it('keeps synthetic Activity cursors reloadable and bound to dataset and page size', () => {
  const first = new DemoProjector(structuredClone(f7) as World).read(new URL('http://localhost/api/v1/activity?limit=50'));
  const token = (first.body as { data: { next_cursor: string } }).data.next_cursor;
  const route = new URL('http://localhost/api/v1/activity?limit=50');
  route.searchParams.set('cursor', token);
  const reloaded = new DemoProjector(structuredClone(f7) as World).read(route);
  expect(reloaded.status).toBe(200);
  expect((reloaded.body as { data: { items: unknown[] } }).data.items).toHaveLength(11);
  expect(new DemoProjector(structuredClone(f1) as World).read(route).status).toBe(400);
  route.searchParams.set('limit', '25');
  expect(new DemoProjector(structuredClone(f7) as World).read(route).status).toBe(400);
});

it('keeps older Activity pages pinned when the control revision advances', () => {
  const server = new DemoProjector(structuredClone(f7) as World);
  const route = new URL('http://localhost/api/v1/activity?limit=25');
  const first = server.read(route);
  const page = (body: unknown) => body as {
    control_revision: string; data: { items: unknown[]; next_cursor: string }
  };
  route.searchParams.set('cursor', page(first.body).data.next_cursor);
  const older = page(server.read(route).body);
  server.changeRevision('99');
  const refreshed = server.read(route);
  expect(refreshed.status).toBe(200);
  expect(page(refreshed.body).control_revision).toBe('99');
  expect(page(refreshed.body).data).toEqual(older.data);
});
