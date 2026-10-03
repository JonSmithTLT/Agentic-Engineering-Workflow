import { render, screen, act, within } from '@testing-library/react';
import {
  QueryClient,
  QueryClientProvider,
  QueryObserver,
} from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { DashboardProvider, PageSnapshot } from '../src/client/dashboard';
import { HistoryDetailPage } from '../src/pages/History';
import { useProjection, installVisibility } from '../src/client/queries';
import { installRevisionReconciliation } from '../src/client/revisions';
import { responseSchemas } from '../src/api/schema';
import { historyLinkRelations } from '../src/api/vocabulary';
import { DemoProjector } from '../src/api/mock/projector';
import type { World } from '../src/api/mock/types';
import f1 from '../src/api/mock/fixtures/F1.json';
import f3 from '../src/api/mock/fixtures/F3.json';
function visible(value: boolean) {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: value ? 'visible' : 'hidden',
  });
  document.dispatchEvent(new Event('visibilitychange'));
}
it('FR-1: every contract link relation is recognized and navigates by relation; unknown targets stay text', async () => {
  visible(true);
  const world = structuredClone(f3) as World;
  const record = responseSchemas.HistoryResponse.parse(
    world.responses['/history/T-0004'],
  );
  expect(Object.keys(record.data.links).sort()).toEqual(
    [...historyLinkRelations].sort(),
  );
  record.data.links.future_relation = ['UNKNOWN-0001'];
  world.responses['/history/T-0004'] = record;
  const server = new DemoProjector(world);
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
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
      <MemoryRouter initialEntries={['/history/T-0004']}>
        <DashboardProvider>
          <Routes>
            <Route path="/history/:id" element={<HistoryDetailPage />} />
          </Routes>
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const heading = await screen.findByRole('heading', {
    name: 'Lineage and links',
  });
  const section = heading.closest('section')!;
  const dt = [...section.querySelectorAll('dt')];
  for (const relation of historyLinkRelations) {
    const term = dt.find(
      (node) => node.textContent?.replaceAll(' ', '_') === relation,
    )!;
    expect(term, relation).toBeTruthy();
    expect(term.querySelector('.unknown'), relation).toBeNull();
    const links = term.nextElementSibling!.querySelectorAll('a');
    const hrefs = [...links].map((link) => link.getAttribute('href'));
    if (relation === 'invocations') expect(hrefs).toEqual(['/runs/INV-0001']);
    else if (relation === 'evidence')
      expect(hrefs).toEqual(['/evidence/INV-0001-verification-1']);
    else if (['tokens', 'integration_commit'].includes(relation))
      expect(hrefs).toEqual([]);
    else
      expect(
        hrefs.every(
          (href) => href?.startsWith('/work/') || href?.startsWith('/history/'),
        ),
      ).toBe(true);
  }
  expect(within(section).getByText('TOKEN-0001').closest('a')).toBeNull();
  expect(within(section).getByText('UNKNOWN-0001').closest('a')).toBeNull();
  expect(
    within(section).getByText('future_relation').closest('.unknown'),
  ).toBeTruthy();
  // Annotation vocabulary still recognizes lineage even though History.links does not.
  expect(within(section).getByText('lineage').closest('.unknown')).toBeNull();
  rendered.unmount();
  client.clear();
});
async function churn(pinned: boolean) {
  visible(true);
  vi.useFakeTimers({
    toFake: [
      'setTimeout',
      'clearTimeout',
      'setInterval',
      'clearInterval',
      'Date',
      'performance',
    ],
  });
  const start = Date.now();
  const requests: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const route = new URL(String(input), 'http://localhost').pathname.slice(
      '/api/v1'.length,
    );
    requests.push(route);
    const payload = structuredClone((f1 as World).responses[route]) as {
      control_revision: string;
      generated_at: string;
    };
    const revision =
      pinned && route === '/project'
        ? 0
        : Math.floor((Date.now() - start) / 3000);
    payload.control_revision = String(revision);
    payload.generated_at = new Date(
      Date.UTC(2026, 9, 2, 12, 0, 0) + revision * 3000,
    ).toISOString();
    const tag = `"${route}:${revision}"`;
    const same = new Headers(init?.headers).get('If-None-Match') === tag;
    return new Promise((resolve) =>
      setTimeout(
        () =>
          resolve(
            same
              ? new Response(null, { status: 304, headers: { ETag: tag } })
              : new Response(JSON.stringify(payload), {
                  headers: { 'Content-Type': 'application/json', ETag: tag },
                }),
          ),
        25,
      ),
    );
  });
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false },
    },
  });
  const dispose = installVisibility(client);
  function Probe() {
    const detail = useProjection(
      '/work/T-0001',
      responseSchemas.WorkResponse,
      'detail',
    );
    const history = useProjection(
      '/history',
      responseSchemas.HistoryListResponse,
      'history',
    );
    return <PageSnapshot queries={[detail, history]} />;
  }
  const rendered = render(
    <QueryClientProvider client={client}>
      <DashboardProvider>
        <Probe />
      </DashboardProvider>
    </QueryClientProvider>,
  );
  let warning = false;
  for (let i = 0; i < 600; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    warning ||= !!screen.queryByText(/Mixed revisions persist/);
  }
  await act(async () => {
    await vi.advanceTimersByTimeAsync(100);
  });
  const values = client
    .getQueryCache()
    .findAll({ queryKey: ['projection'], type: 'active' })
    .map(
      (q) =>
        (q.state.data as { value: { control_revision: string } }).value
          .control_revision,
    );
  const result = { warning, requests, values };
  rendered.unmount();
  dispose();
  client.clear();
  vi.useRealTimers();
  visible(true);
  return result;
}
it('FR-2: advancing every 3 seconds for 60 seconds catches slower and manual projections up without a persistent warning', async () => {
  const result = await churn(false);
  expect(result.warning).toBe(false);
  expect(new Set(result.values).size).toBe(1);
  expect(
    result.requests.filter((route) => route === '/project').length,
  ).toBeGreaterThan(10);
  expect(
    result.requests.filter((route) => route === '/history').length,
  ).toBeGreaterThan(10);
  expect(result.requests.length).toBeLessThan(200);
}, 15000);
it('FR-2 negative control: server-pinned old 304 representations still trigger the warning without a retry storm', async () => {
  const result = await churn(true);
  expect(result.warning).toBe(true);
  expect(new Set(result.values).size).toBeGreaterThan(1);
  expect(result.requests.length).toBeLessThan(200);
}, 15000);
it('FR-2 excludes hidden, disabled and other-project projections and compares large revisions exactly', async () => {
  visible(false);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  const value = (project: string, revision: string) => ({
    value: { project_id: project, control_revision: revision },
    last_checked_at: '2026-10-02T12:00:00Z',
  });
  const project = vi.fn().mockResolvedValue(value('p', '9007199254740993'));
  const disabled = vi.fn();
  const other = vi.fn();
  const specs = [
    ['/project', value('p', '9007199254740992'), project, true],
    ['/overview', value('p', '9007199254740993'), vi.fn(), true],
    ['/evidence', value('p', '0'), disabled, false],
    ['/foreign', value('other', '0'), other, true],
  ] as const;
  const observers = specs.map(([route, data, fn, enabled]) => {
    const key = ['projection', route];
    client.setQueryData(key, data);
    const observer = new QueryObserver(client, {
      queryKey: key,
      queryFn: fn,
      enabled,
      staleTime: Infinity,
    });
    return observer.subscribe(() => {});
  });
  const dispose = installRevisionReconciliation(client);
  await Promise.resolve();
  expect(project).not.toHaveBeenCalled();
  visible(true);
  await Promise.resolve();
  await Promise.resolve();
  expect(project).toHaveBeenCalledTimes(1);
  expect(disabled).not.toHaveBeenCalled();
  expect(other).not.toHaveBeenCalled();
  dispose();
  observers.forEach((unsubscribe) => unsubscribe());
  client.clear();
  visible(true);
});
