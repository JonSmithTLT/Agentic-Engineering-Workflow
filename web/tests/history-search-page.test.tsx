import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { DashboardProvider } from '../src/client/dashboard';
import { queryClient } from '../src/client/queries';
import { historySearchSession } from '../src/client/history-search';
import { HistorySearchPage } from '../src/pages/HistorySearch';
import { DemoProjector } from '../src/api/mock/projector';
import type { World } from '../src/api/mock/types';
import f1 from '../src/api/mock/fixtures/F1.json';
beforeEach(() => { queryClient.clear(); historySearchSession.clear(); });
afterEach(() => { queryClient.clear(); historySearchSession.clear(); });
function mount(off = false, pause?: () => Promise<void>) {
  const world = structuredClone(f1) as World;
  if (off) delete (world.responses['/capabilities'] as { data: Record<string, unknown> }).data.history_search;
  const projector = new DemoProjector(world);
  const reads: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = new URL(String(input), 'http://localhost');
    reads.push(url.href);
    if (url.pathname === '/api/v1/history/search' && pause) await pause();
    const response = projector.read(url);
    return new Response(JSON.stringify(response.body), { status: response.status, headers: { 'Content-Type': 'application/json' } });
  });
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={['/history/search']}><DashboardProvider><Routes>
    <Route path="/history/search" element={<HistorySearchPage />} />
    <Route path="/history/T-0004" element={<><h1>Archived record</h1><Link to="/history/search">Return to search</Link></>} />
  </Routes></DashboardProvider></MemoryRouter></QueryClientProvider>);
  return reads;
}
it('Clear during a pending search focuses the re-enabled first term and rejects its late result', async () => {
  let release!: () => void;
  mount(false, () => new Promise<void>(resolve => { release = resolve; }));
  const input = await screen.findByLabelText('Term 1');
  fireEvent.change(input, { target: { value: 'fictional' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));
  await waitFor(() => expect(release).toBeDefined());
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  await waitFor(() => expect(document.activeElement).toBe(input));
  expect(input.closest('fieldset')?.disabled).toBe(false);
  release();
  await waitFor(() => expect(screen.queryByRole('heading', { name: 'Submitted search results' })).toBeNull());
});
it('requires explicit submission and keeps fictional hostile snippets inert', async () => {
  const reads = mount();
  const input = await screen.findByLabelText('Term 1');
  fireEvent.change(input, { target: { value: 'fictional' } });
  window.dispatchEvent(new Event('focus'));
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));
  await screen.findByRole('heading', { name: 'Submitted search results' });
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(1);
  expect(document.querySelector('.search-snippet script')).toBeNull();
  expect(document.querySelector('a[href="https://example.invalid"]')).toBeNull();
  expect(screen.getByText('Incomplete search coverage')).toBeDefined();
  fireEvent.change(input, { target: { value: 'other draft' } });
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  expect((input as HTMLInputElement).value).toBe('');
  expect(document.activeElement).toBe(input);
  expect(screen.queryByRole('heading', { name: 'Submitted search results' })).toBeNull();
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(1);
});
it('does not execute the absent route from a direct link', async () => {
  const reads = mount(true);
  await screen.findByText('Raw history search is not offered on this project.');
  expect(screen.queryByRole('button', { name: 'Search' })).toBeNull();
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(0);
});
it('blocks IME submission and exposes/focuses associated invalid UTC fields', async () => {
  const reads = mount();
  const input = await screen.findByLabelText('Term 1');
  fireEvent.change(input, { target: { value: 'fictional' } });
  fireEvent.compositionStart(input);
  fireEvent.submit(input.closest('form')!);
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(0);
  fireEvent.compositionEnd(input);
  const since = screen.getByLabelText('Since (UTC)');
  fireEvent.change(since, { target: { value: 'yesterday' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));
  expect(since.getAttribute('aria-invalid')).toBe('true');
  expect(document.activeElement).toBe(since);
  expect(document.getElementById(since.getAttribute('aria-describedby')!)).not.toBeNull();
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(0);
});
it('returns to its in-memory submitted result without a search read', async () => {
  const reads = mount();
  fireEvent.change(await screen.findByLabelText('Term 1'), { target: { value: 'fictional' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));
  fireEvent.click(await screen.findByRole('link', { name: 'Archived removal reference' }));
  await screen.findByRole('heading', { name: 'Archived record' });
  fireEvent.click(screen.getByRole('link', { name: 'Return to search' }));
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Submitted search results' })).toBeDefined());
  expect(reads.filter(url => url.includes('/history/search'))).toHaveLength(1);
});
