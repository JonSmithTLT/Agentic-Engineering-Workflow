import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { workGraph } from '../src/pages/work-graph-model';
import { WorkGraph } from '../src/components/WorkGraph';
import { DashboardProvider } from '../src/client/dashboard';
import { responseSchemas } from '../src/api/schema';
import { workRoute } from '../src/pages/work-model';
import { DemoProjector } from '../src/api/mock/projector';
import f1 from '../src/api/mock/fixtures/F1.json';
import f6 from '../src/api/mock/fixtures/F6.json';
import type { World } from '../src/api/mock/types';
const items = responseSchemas.WorkListResponse.parse(f1.responses['/work']).data
  .items;
it('graph lays out only loaded parent links, preserving backend counts and source objects', () => {
  const before = JSON.stringify(items);
  const graph = workGraph(items, new Set());
  expect(
    graph.edges.some(
      (edge) => edge.parent.id === 'E-0001' && edge.child.id === 'S-0001',
    ),
  ).toBe(true);
  const ticket = graph.nodes.find((node) => node.id === 'T-0001')!,
    story = graph.nodes.find((node) => node.id === 'S-0001')!;
  expect(ticket.x).toBeGreaterThan(story.x);
  expect(
    graph.nodes.find((node) => node.id === 'E-0001')!.item!.rollup,
  ).toEqual(items.find((item) => item.id === 'E-0001')!.rollup);
  expect(JSON.stringify(items)).toBe(before);
});
it('graph distinguishes unloaded parent references and never gives them an invented state/title', () => {
  const onlyTicket = items.filter((item) => item.id === 'T-0001');
  const graph = workGraph(onlyTicket, new Set());
  const parent = graph.nodes.find((node) => node.id === 'S-0001')!;
  expect(parent.item).toBeUndefined();
  expect(graph.edges).toHaveLength(1);
  expect(graph.nodes).toHaveLength(2);
});
it('focus, collapsed branches, absent focus and cyclic references stay bounded', () => {
  const focused = workGraph(items, new Set(), 'S-0001');
  expect(focused.nodes.some((node) => node.id === 'E-0001')).toBe(false);
  expect(focused.nodes.some((node) => node.id === 'T-0001')).toBe(true);
  const collapsed = workGraph(items, new Set(['S-0001']));
  expect(collapsed.nodes.some((node) => node.id === 'T-0001')).toBe(false);
  expect(collapsed.nodes.some((node) => node.id === 'S-0001')).toBe(true);
  expect(workGraph(items, new Set(), 'MISSING').focusMissing).toBe(true);
  const cycle = items
    .slice(0, 2)
    .map((item, index) => ({
      ...item,
      id: index ? 'B' : 'A',
      parent_id: index ? 'A' : 'B',
    }));
  const result = workGraph(cycle, new Set());
  expect(result.nodes).toHaveLength(2);
  expect(result.edges).toHaveLength(2);
  expect(
    result.nodes.every(
      (node) => Number.isFinite(node.x) && Number.isFinite(node.y),
    ),
  ).toBe(true);
  expect(workGraph(cycle, new Set(['A'])).nodes.map((node) => node.id)).toEqual(
    ['A'],
  );
});
it('a large page graph stays at 100 supplied records plus one explicit unloaded parent', () => {
  const page = responseSchemas.WorkListResponse.parse(f6.responses['/work'])
    .data.items;
  const graph = workGraph(page, new Set());
  expect(graph.nodes.filter((node) => node.item)).toHaveLength(100);
  expect(graph.nodes.filter((node) => !node.item)).toHaveLength(1);
  expect(graph.edges).toHaveLength(100);
  expect(
    workRoute(new URLSearchParams('view=graph&focus=S-0001&fixture=F6')),
  ).toBe('/work?limit=100');
});
it('native graph controls select, collapse, focus and zoom without issuing graph or per-node requests', async () => {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: 'visible',
  });
  const server = new DemoProjector(f1 as World);
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
      <MemoryRouter initialEntries={['/work?view=graph']}>
        <DashboardProvider>
          <WorkGraph items={items} />
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole('button', { name: /Select T-0001:/ });
  fireEvent.click(screen.getByRole('button', { name: /Select T-0001:/ }));
  await screen.findByRole('link', { name: 'Open Work detail' });
  expect(
    screen.getByRole('link', { name: 'Open Work detail' }).getAttribute('href'),
  ).toBe('/work/T-0001');
  fireEvent.click(
    screen.getByRole('button', { name: 'Collapse branch S-0001' }),
  );
  expect(screen.queryByRole('button', { name: /Select T-0001:/ })).toBeNull();
  expect(
    screen.getByText(
      'The selection is hidden by this focus or a collapsed branch.',
    ),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
  expect(screen.getByRole('button', { name: /Select T-0001:/ })).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Graph focus'), {
    target: { value: 'S-0001' },
  });
  expect(screen.queryByRole('button', { name: /Select E-0001:/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Zoom out' }));
  expect(screen.getByLabelText('Zoom level').textContent).toBe('85%');
  expect(
    request.mock.calls.every(
      ([url]) =>
        !String(url).includes('/graph') && !String(url).includes('/work/'),
    ),
  ).toBe(true);
  rendered.unmount();
  client.clear();
});
