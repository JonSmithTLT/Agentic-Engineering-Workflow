import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardProvider } from '../src/client/dashboard';
import { queryClient, installVisibility } from '../src/client/queries';
import { transport } from '../src/api/transport';
import { MapsPage } from '../src/pages/Maps';
import { DemoProjector } from '../src/api/mock/projector';
import { fixtureMapRoots } from '../src/api/mock/maps-fixtures';
import type { World } from '../src/api/mock/types';
import f1 from '../src/api/mock/fixtures/F1.json';
beforeEach(() => { queryClient.clear(); transport.reset(); });
afterEach(() => { queryClient.clear(); transport.reset(); });
function mount(search = '', corrupt = false, intercept?: (url: URL, body: unknown) => Response | undefined) {
  const projector = new DemoProjector(structuredClone(f1) as World);
  const reads: URL[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = new URL(String(input), 'http://localhost'); reads.push(url);
    const result = projector.read(url);
    if (corrupt && /\/maps\/structural\/[a-f0-9]+$/.test(url.pathname)) (result.body as { data: { summary: { root: string } } }).data.summary.root = 'f'.repeat(64);
    const intercepted = intercept?.(url, result.body);
    if (intercepted) return intercepted;
    return new Response(JSON.stringify(result.body), { status: result.status, headers: { 'Content-Type': 'application/json' } });
  });
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={['/maps' + search]}><DashboardProvider><MapsPage /></DashboardProvider></MemoryRouter></QueryClientProvider>);
  return reads;
}
it('invalid presentation sends no Maps request after bootstrap', async () => {
  const reads = mount('?map_root=HEAD');
  await screen.findByRole('alert');
  await waitFor(() => expect(reads.some(url => url.pathname.endsWith('/capabilities'))).toBe(true));
  expect(reads.filter(url => url.pathname.includes('/maps'))).toHaveLength(0);
});
it('reads only the displayed input page, keeps hostile paths inert and replaces the page', async () => {
  const reads = mount(`?map_root=${fixtureMapRoots[0]}&map_tab=inputs`);
  await screen.findByText('<script>window.__mapsHostile=1</script>');
  expect(document.querySelector('.map-detail script')).toBeNull();
  expect(reads.some(url => /\/structural\/[a-f0-9]+$/.test(url.pathname))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  await screen.findByText('src/fictional-060.ts');
  expect(screen.queryByText('<script>window.__mapsHostile=1</script>')).toBeNull();
  const cached = queryClient.getQueryCache().findAll().filter(query => String(query.queryKey.at(-1)).includes('/inputs'));
  expect(cached).toHaveLength(1);
});
it('foreground revalidates displayed summary but cannot refresh manual map detail', async () => {
  const reads = mount();
  await screen.findByRole('heading', { name: 'Map root ' + fixtureMapRoots[0] });
  await screen.findByText('Rows omitted');
  const detailBefore = reads.filter(url => /\/structural\/[a-f0-9]+$/.test(url.pathname)).length;
  const summaryBefore = reads.filter(url => url.pathname.endsWith('/maps')).length;
  const dispose = installVisibility(queryClient);
  try {
    window.dispatchEvent(new Event('focus'));
    await waitFor(() => expect(reads.filter(url => url.pathname.endsWith('/maps')).length).toBeGreaterThan(summaryBefore));
    expect(reads.filter(url => /\/structural\/[a-f0-9]+$/.test(url.pathname))).toHaveLength(detailBefore);
  } finally { dispose(); }
});
it('rejects a detail bound to a different root before rendering its body', async () => {
  mount(`?map_root=${fixtureMapRoots[0]}`, true);
  await screen.findByRole('alert');
  expect(screen.queryByText('Rows omitted')).toBeNull();
});
it('retains valid detail on ordinary refresh failure and clears it on refusal', async () => {
  let status = 200;
  mount('', false, url => /\/structural\/[a-f0-9]+$/.test(url.pathname) && status !== 200
    ? new Response(JSON.stringify({ error: { code: status === 403 ? 'ACCESS_DENIED' : 'SERVER_BUSY', message: 'Fictional failure' } }), { status, headers: { 'Content-Type': 'application/json' } }) : undefined);
  await screen.findByText('Rows omitted');
  status = 503;
  fireEvent.click(screen.getAllByRole('button', { name: 'Refresh this projection' })[1]);
  await screen.findByRole('alert');
  expect(screen.getByText('Rows omitted')).toBeTruthy();
  expect(screen.getByRole('alert').textContent).toContain('last-known-good');
  status = 403;
  fireEvent.click(screen.getAllByRole('button', { name: 'Refresh this projection' })[1]);
  await waitFor(() => expect(screen.queryByText('Rows omitted')).toBeNull());
});
it('renders an empty registry without selecting an inferred map', async () => {
  const reads = mount('', false, (url, body) => {
    if (!url.pathname.endsWith('/maps')) return;
    const value = body as { data: { registry: { state: string }; structural: { state: string; summary: unknown; freshness: unknown } } };
    value.data.registry.state = 'NONE';
    value.data.structural = { ...value.data.structural, state: 'UNAVAILABLE', summary: null, freshness: null };
    return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
  });
  await screen.findByText('No selected map supplied. Use Stored maps to choose an available root.');
  expect(reads.some(url => /\/structural\/[a-f0-9]+$/.test(url.pathname))).toBe(false);
});
