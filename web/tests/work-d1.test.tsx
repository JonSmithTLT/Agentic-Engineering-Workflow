import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { DashboardProvider } from '../src/client/dashboard';
import { WorkPage } from '../src/pages/Work';
import { WorkTable } from '../src/components/WorkTable';
import { workRoute, workTree, type Work } from '../src/pages/work-model';
import { DemoProjector } from '../src/api/mock/projector';
import type { World } from '../src/api/mock/types';
import f3 from '../src/api/mock/fixtures/F3.json';
import f6 from '../src/api/mock/fixtures/F6.json';
import f9 from '../src/api/mock/fixtures/F9.json';
import { responseSchemas } from '../src/api/schema';
beforeEach(() =>
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: 'visible',
  }),
);
function mount(node: React.ReactNode, world: World, route = '/work') {
  const server = new DemoProjector(world);
  const request = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async (input) => {
      const result = server.read(
        new URL(String(input), 'http://localhost'),
      );
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
        <DashboardProvider>{node}</DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return {
    request,
    client,
    rerender: (next: React.ReactNode) =>
      rendered.rerender(
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={[route]}>
            <DashboardProvider>{next}</DashboardProvider>
          </MemoryRouter>
        </QueryClientProvider>,
      ),
  };
}
it('work request scopes use only accepted filters, limit and opaque cursor', () => {
  expect(
    workRoute(
      new URLSearchParams(
        'fixture=F3&fault=500&state=DONE&parent=S-0001&cursor=opaque%3A%2B%2F%3D',
      ),
    ),
  ).toBe(
    '/work?limit=100&state=DONE&parent=S-0001&cursor=opaque%3A%2B%2F%3D',
  );
});
it('loaded hierarchy is bounded, collapsible and cycle safe without deriving rollups', () => {
  const data = responseSchemas.WorkListResponse.parse(f3.responses['/work'])
    .data.items;
  const tree = workTree(data, new Set());
  expect(tree.find((x) => x.item.id === 'T-0001')?.depth).toBe(2);
  expect(
    workTree(data, new Set(['S-0001'])).some((x) => x.item.id === 'T-0001'),
  ).toBe(false);
  const a = { ...data[0], id: 'A', parent_id: 'B' },
    b = { ...data[1], id: 'B', parent_id: 'A' };
  expect(workTree([a, b], new Set()).map((x) => x.item.id)).toEqual([
    'A',
    'B',
  ]);
  expect(data[0].rollup).toEqual({ open: 3, done: 1, cancelled: 0 });
});
it('changing terminal state filter reaches older archived work with server filtering', async () => {
  const { request, client } = mount(<WorkPage />, f3 as World);
  await screen.findByRole('heading', { name: 'Work records' });
  fireEvent.change(screen.getByLabelText('State filter'), {
    target: { value: 'DONE' },
  });
  await waitFor(() =>
    expect(
      request.mock.calls.some(([url]) =>
        String(url).includes('state=DONE'),
      ),
    ).toBe(true),
  );
  fireEvent.click(await screen.findByRole('checkbox'));
  await screen.findByText('Finished check 28');
  expect(
    request.mock.calls.every(([, init]) => init?.method === 'GET'),
  ).toBe(true);
  client.clear();
});
it('virtualized page renders a bounded window and provides an accessible complete-page view', async () => {
  const items = responseSchemas.WorkListResponse.parse(
    f6.responses['/work'],
  ).data.items;
  const { client } = mount(
    <WorkTable items={items as Work[]} tree={false} />,
    f6 as World,
  );
  await screen.findByRole('link', { name: 'Projection check 1' });
  expect(screen.getAllByRole('row').length).toBeLessThan(30);
  const viewport = screen.getByLabelText('Work rows');
  fireEvent.scroll(viewport, { target: { scrollTop: 2800 } });
  await screen.findByRole('link', { name: 'Projection check 90' });
  expect(
    screen.queryByRole('link', { name: 'Projection check 1' }),
  ).toBeNull();
  fireEvent.click(screen.getByRole('checkbox'));
  await screen.findByRole('link', { name: 'Projection check 100' });
  expect(screen.getAllByRole('row')).toHaveLength(101);
  client.clear();
});
it('unsupported work suppresses list requests and renders backend explanation', async () => {
  const world = structuredClone(f9) as World;
  const caps = world.responses['/capabilities'] as {
    data: Record<string, unknown>;
  };
  caps.data.work = {
    state: 'UNSUPPORTED',
    reasons: [
      {
        code: 'not_supported',
        message: 'No Work projection in this version',
      },
    ],
  };
  const { request, client } = mount(<WorkPage />, world);
  await screen.findByText('No Work projection in this version', {
    exact: false,
  });
  expect(
    request.mock.calls.some(([url]) =>
      String(url).startsWith('/api/v1/work'),
    ),
  ).toBe(false);
  client.clear();
});

it('shrinking a refreshed page clamps the virtual window rather than leaving blank rows', async () => {
  const items = responseSchemas.WorkListResponse.parse(
    f6.responses['/work'],
  ).data.items;
  const { client, rerender } = mount(
    <WorkTable items={items} tree={false} />,
    f6 as World,
  );
  await screen.findByRole('link', { name: 'Projection check 1' });
  fireEvent.scroll(screen.getByLabelText('Work rows'), {
    target: { scrollTop: 2800 },
  });
  await screen.findByRole('link', { name: 'Projection check 90' });
  rerender(<WorkTable items={items.slice(0, 3)} tree={false} />);
  await screen.findByRole('link', { name: 'Projection check 1' });
  expect(screen.getAllByRole('row')).toHaveLength(4);
  client.clear();
});
