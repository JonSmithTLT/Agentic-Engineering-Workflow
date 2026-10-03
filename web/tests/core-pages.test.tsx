import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { DashboardProvider } from '../src/client/dashboard';
import {
  RunsPage,
  RunDetailPage,
  EvidencePage,
  EvidenceDetailPage,
  KnowledgePage,
  KnowledgeDetailPage,
} from '../src/pages/Records';
import { HistoryPage, HistoryDetailPage } from '../src/pages/History';
import { AttentionPage, QueuePage } from '../src/pages/Attention';
import { listRoute } from '../src/components/ProjectionViews';
import { DemoProjector } from '../src/api/mock/projector';
import type { World } from '../src/api/mock/types';
import f1 from '../src/api/mock/fixtures/F1.json';
import f3 from '../src/api/mock/fixtures/F3.json';
import f4 from '../src/api/mock/fixtures/F4.json';
import f7 from '../src/api/mock/fixtures/F7.json';
import f9 from '../src/api/mock/fixtures/F9.json';
import { responseSchemas } from '../src/api/schema';
beforeEach(() =>
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: 'visible',
  }),
);
function mount(node: React.ReactNode, route: string, fixture = f1 as World) {
  const world = structuredClone(fixture);
  const server = new DemoProjector(world);
  const request = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async (input) => {
      const result = server.read(new URL(String(input), 'http://localhost'));
      return new Response(JSON.stringify(result.body), {
        status: result.status,
        headers: { 'Content-Type': 'application/json' },
      });
    });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const rendered = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <DashboardProvider>
          <Routes>
            <Route path="*" element={node} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
            <Route path="/evidence/:id" element={<EvidenceDetailPage />} />
            <Route path="/knowledge/:id" element={<KnowledgeDetailPage />} />
            <Route path="/history/:id" element={<HistoryDetailPage />} />
          </Routes>
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { request, client, server, world, rendered };
}
it('list scopes strip demo and foreign filters, retaining accepted opaque cursor values', () => {
  expect(
    listRoute(
      '/evidence',
      new URLSearchParams(
        'fixture=F1&work=T-0001&kind=unit&cursor=opaque%3A%2F%3D',
      ),
      ['work'],
    ),
  ).toBe('/evidence?limit=100&work=T-0001&cursor=opaque%3A%2F%3D');
});
it('Runs includes invocations without harness runs and links to nested harness inspection', async () => {
  const { client } = mount(<RunsPage />, '/runs');
  await screen.findByRole('link', { name: 'INV-0002' });
  expect(screen.getByText('No harness runs supplied')).toBeTruthy();
  fireEvent.click(screen.getByRole('link', { name: 'INV-0001' }));
  await screen.findByRole('heading', { name: 'Harness runs' });
  expect(screen.getByText('R-INV-0001-1')).toBeTruthy();
  expect(
    screen
      .getByRole('link', { name: 'Contract verification' })
      .getAttribute('href'),
  ).toBe('/evidence/INV-0001-verification-1');
  client.clear();
});
it('Evidence filter is sent to backend and an invalid ID suppresses the request', async () => {
  const { request, client } = mount(<EvidencePage />, '/evidence?work=T-0001');
  await screen.findByRole('link', { name: 'INV-0001-verification-1' });
  expect(
    request.mock.calls.some(([url]) =>
      String(url).includes('/evidence?limit=100&work=T-0001'),
    ),
  ).toBe(true);
  const before = request.mock.calls.length;
  fireEvent.change(screen.getByLabelText('Evidence work filter'), {
    target: { value: '../unsafe' },
  });
  await screen.findByRole('alert');
  expect(
    request.mock.calls
      .slice(before)
      .some(([url]) => String(url).includes('/evidence')),
  ).toBe(false);
  client.clear();
});
it('Evidence displays backend stale currentness, bindings and escaped code without remote images', async () => {
  const world = structuredClone(f1) as World;
  const record = responseSchemas.EvidenceResponse.parse(
    world.responses['/evidence/INV-0001-verification-1'],
  );
  record.data.currentness = 'STALE';
  record.data.body.text =
    '![remote](https://untrusted.invalid/pixel)\n<script>bad()</script>\n\n```html\n<script>literal()</script>\n```';
  world.responses['/evidence/INV-0001-verification-1'] = record;
  const { client } = mount(
    <EvidenceDetailPage />,
    '/evidence/INV-0001-verification-1',
    world,
  );
  await screen.findByText(
    'AEW reports STALE evidence. Do not treat this record as current evidence.',
  );
  expect(document.querySelector('img,script')).toBeNull();
  expect(screen.getByText('<script>literal()</script>')).toBeTruthy();
  fireEvent.click(screen.getByText('Evaluated snapshot and plan bindings'));
  expect(screen.getByText(/git-tree:32381523/)).toBeTruthy();
  expect(
    screen.getByRole('link', { name: 'INV-0001' }).getAttribute('href'),
  ).toBe('/runs/INV-0001');
  client.clear();
});
it('Knowledge groups page records and warns on unregistered semantic states', async () => {
  const { client } = mount(<KnowledgePage />, '/knowledge');
  await screen.findByRole('link', {
    name: 'Keep dashboard inspection read-only',
  });
  expect(screen.getByText('decision')).toBeTruthy();
  expect(screen.getByText('ACCEPTED')).toBeTruthy();
  expect(screen.getByText(/Unknown value:/)).toBeTruthy();
  fireEvent.click(
    screen.getByRole('link', { name: 'Keep dashboard inspection read-only' }),
  );
  await screen.findByRole('heading', { name: 'Provenance' });
  expect(
    screen.getByRole('link', { name: 'Contract checks' }).getAttribute('href'),
  ).toBe('/evidence/INV-0001-verification-1');
  client.clear();
});
it('History holds a bounded cursor window over 50000 records without requesting integrity when unsupported', async () => {
  const { request, client } = mount(
    <HistoryPage />,
    '/history?fixture=F7',
    f7 as World,
  );
  await screen.findByRole('link', { name: 'T-H000100' });
  expect(screen.queryByRole('link', { name: 'T-H000101' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  await screen.findByRole('link', { name: 'T-H000101' });
  expect(
    request.mock.calls.some(([url]) =>
      String(url).includes('cursor=demo-cursor-'),
    ),
  ).toBe(true);
  expect(
    request.mock.calls.some(([url]) =>
      String(url).includes('/history/integrity'),
    ),
  ).toBe(false);
  expect(
    screen.getByText(/Archived records are never current evidence/),
  ).toBeTruthy();
  client.clear();
});
it('History annotations are separately bounded and keep content hashes and trust labels', async () => {
  const world = structuredClone(f3) as World;
  const original = responseSchemas.HistoryResponse.parse(
    world.responses['/history/T-0004'],
  );
  const template = original.data.annotations[0];
  world.responses['/history/T-0004'] = {
    ...original,
    data: {
      ...original.data,
      annotations: Array.from({ length: 205 }, (_, i) => ({
        ...template,
        id: `AN-${i + 1}`,
      })),
    },
  };
  const { request, client } = mount(
    <HistoryDetailPage />,
    '/history/T-0004',
    world,
  );
  await screen.findByText('AN-100');
  expect(screen.queryByText('AN-101')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  await screen.findByText('AN-101');
  expect(
    request.mock.calls.some(([url]) =>
      String(url).includes(
        'annotations_limit=100&annotations_cursor=demo-cursor-',
      ),
    ),
  ).toBe(true);
  expect(screen.getByText(original.data.sha256)).toBeTruthy();
  expect(
    screen
      .getAllByRole('link', { name: 'S-0001' })
      .find((link) => link.getAttribute('href') === '/work/S-0001')
      ?.getAttribute('href'),
  ).toBe('/work/S-0001');
  client.clear();
});
it('invalid history dates suppress list requests, not the capability explanation', async () => {
  const { request, client } = mount(
    <HistoryPage />,
    '/history?since=not-a-date',
  );
  await screen.findByText('Check the filter values. No request was sent.');
  await waitFor(() =>
    expect(
      request.mock.calls.some(([url]) => String(url).includes('/capabilities')),
    ).toBe(true),
  );
  expect(
    request.mock.calls.some(([url]) =>
      String(url).includes('/api/v1/history?'),
    ),
  ).toBe(false);
  client.clear();
});
it('available integrity renders backend structured roots and backlog without calculating audit health', async () => {
  const world = structuredClone(f4) as World;
  const caps = responseSchemas.CapabilitiesResponse.parse(
    world.responses['/capabilities'],
  );
  caps.data.integrity = { state: 'AVAILABLE', reasons: [] };
  world.responses['/capabilities'] = caps;
  world.responses['/history/integrity'] =
    world.provisional_responses['/history/integrity'];
  const { client } = mount(<HistoryPage />, '/history', world);
  await screen.findByText('CORRUPTION_REPORTED');
  expect(
    screen.getByText('Unverified backlog').nextElementSibling?.textContent,
  ).toBe('2');
  expect(screen.getByText(/Hypothetical P2c backend finding/)).toBeTruthy();
  expect(screen.getByText('2026-10-02T11:30:00Z')).toBeTruthy();
  client.clear();
});
it('Attention reads backend decisions and Queue never invents a read endpoint', async () => {
  const { request, client, rendered } = mount(<AttentionPage />, '/attention');
  await screen.findByRole('heading', { name: 'Disposition required' });
  expect(
    screen
      .getByRole('link', { name: 'Review cache provenance' })
      .getAttribute('href'),
  ).toBe('/work/T-0003');
  rendered.unmount();
  client.clear();
  const queue = mount(<QueuePage />, '/queue', f9 as World);
  await screen.findByRole('heading', { name: 'Data unavailable' });
  expect(
    [...request.mock.calls, ...queue.request.mock.calls].some(([url]) =>
      String(url).includes('/api/v1/queue'),
    ),
  ).toBe(false);
  queue.client.clear();
});

it('FR-1 recognized History link relations route to their actual projections without false warnings', async () => {
  const { client } = mount(
    <HistoryDetailPage />,
    '/history/T-0004',
    f3 as World,
  );
  await screen.findByRole('heading', { name: 'Lineage and links' });
  expect(document.querySelector('.unknown')).toBeNull();
  expect(
    screen.getByRole('link', { name: 'INV-0001' }).getAttribute('href'),
  ).toBe('/runs/INV-0001');
  expect(
    screen
      .getByRole('link', { name: 'INV-0001-verification-1' })
      .getAttribute('href'),
  ).toBe('/evidence/INV-0001-verification-1');
  const work = screen
    .getAllByRole('link', { name: 'Work lookup' })
    .map((a) => a.getAttribute('href'));
  const history = screen
    .getAllByRole('link', { name: 'History lookup' })
    .map((a) => a.getAttribute('href'));
  for (const id of ['T-0002', 'S-0001', 'T-0003']) {
    expect(work).toContain('/work/' + id);
    expect(history).toContain('/history/' + id);
  }
  expect(screen.getByText('TOKEN-0001').closest('a')).toBeNull();
  expect(screen.getByText('a'.repeat(40)).closest('a')).toBeNull();
  client.clear();
});
it('FR-1 unknown History link types retain raw warnings and plain target IDs', async () => {
  const world = structuredClone(f3) as World;
  const entry = responseSchemas.HistoryResponse.parse(
    world.responses['/history/T-0004'],
  );
  entry.data.links.future_relation = ['FUTURE-TARGET'];
  world.responses['/history/T-0004'] = entry;
  const { client } = mount(<HistoryDetailPage />, '/history/T-0004', world);
  await screen.findByText('future_relation');
  expect(screen.getByText('future_relation').closest('.unknown')).toBeTruthy();
  expect(screen.getByText('FUTURE-TARGET').closest('a')).toBeNull();
  expect([...document.querySelectorAll('a')].some(a => a.getAttribute('href')?.includes('FUTURE-TARGET'))).toBe(false);
  client.clear();
});
