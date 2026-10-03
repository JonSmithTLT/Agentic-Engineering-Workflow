import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  MemoryRouter,
  Routes,
  Route,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import { DashboardProvider } from '../src/client/dashboard';
import {
  InspectorProvider,
  PresentationGuard,
  RecordInspection,
} from '../src/components/Investigation';
import { WorkPage, WorkDetailPage } from '../src/pages/Work';
import { RunsPage } from '../src/pages/Records';
import { RelationsExplorer } from '../src/components/RelationsExplorer';
import { investigate } from '../src/client/investigation-model';
import { responseSchemas } from '../src/api/schema';
import { ReadTransport, ProjectionHttpError } from '../src/api/transport';
import { dashboardEntityLink, dashboardCopyLink } from '../src/api/navigation';
import { DemoProjector } from '../src/api/mock/projector';
import type { World } from '../src/api/mock/types';
import f1 from '../src/api/mock/fixtures/F1.json';
import f3 from '../src/api/mock/fixtures/F3.json';
import { projectionKey } from '../src/client/queries';
function Location() {
  const location = useLocation(),
    navigate = useNavigate();
  return (
    <>
      <output aria-label="Location">
        {location.pathname + location.search}
      </output>
      <button onClick={() => navigate(-1)}>Back</button>
      <button onClick={() => navigate(1)}>Forward</button>
    </>
  );
}
function mount(
  node: React.ReactNode,
  route = '/work?selected=T-0001',
  world = f1 as World,
) {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: 'visible',
  });
  const server = new DemoProjector(structuredClone(world)),
    paths: string[] = [];
  const request = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async (input) => {
      paths.push(String(input));
      const result = server.read(new URL(String(input), 'http://localhost'));
      return new Response(JSON.stringify(result.body), {
        status: result.status,
        headers: { 'Content-Type': 'application/json', ETag: '"test"' },
      });
    });
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false },
    },
  });
  const rendered = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <DashboardProvider>
          <PresentationGuard>
            <InspectorProvider>
              <Location />
              <Routes>
                <Route path="/work" element={node} />
                <Route path="/work/:id" element={<WorkDetailPage />} />
                <Route path="*" element={node} />
              </Routes>
            </InspectorProvider>
          </PresentationGuard>
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { paths, request, client, rendered };
}
const work = responseSchemas.WorkResponse.parse(f1.responses['/work/T-0001']);
const source = {
  value: work,
  last_checked_at: '2026-10-03T12:00:00Z',
  etag: '"one"',
};
describe('W02 investigation composed behavior', () => {
  it('keeps mounted results, restores URL panels with Back/Forward, and adds no Why request', async () => {
    const { paths } = mount(<WorkPage />);
    await screen.findByRole('heading', { name: work.data.title });
    const results = screen.getByRole('region', {
        name: 'Investigation results',
      }),
      rows = within(results).getByRole('table');
    const count = paths.length;
    fireEvent.click(
      screen.getByRole('button', { name: 'Why state: ' + work.data.state }),
    );
    expect(
      await screen.findByRole('heading', { name: 'Inspect T-0001' }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        'Reasons supplied for this record; no explicit binding to this status.',
      ),
    ).toBeTruthy();
    expect(paths.length).toBe(count);
    expect(within(results).getByRole('table')).toBe(rows);
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() =>
      expect(
        screen.queryByRole('heading', { name: 'Inspect T-0001' }),
      ).toBeNull(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Forward' }));
    await screen.findByRole('heading', { name: 'Inspect T-0001' });
  });
  it('deep-link reload restores Why; unrelated blockers remain separate and Source differs from Browser', async () => {
    mount(
      <WorkPage />,
      '/work?selected=T-0001&inspector=why&field=has_attention',
    );
    await screen.findByRole('heading', { name: 'Inspect T-0001' });
    const inspector = screen.getByRole('complementary', {
      name: 'Investigation inspector',
    });
    expect(
      within(inspector).getByRole('heading', { name: /has_attention:/ }),
    ).toBeTruthy();
    const backend = within(inspector).getByRole('region', {
        name: 'Source provenance',
      }),
      browser = within(inspector).getByRole('region', {
        name: 'Browser observations',
      });
    expect(backend.textContent).not.toContain('Last checked');
    expect(browser.textContent).toContain('Last checked');
    expect(browser.textContent).toContain('not backend health');
  });
  it('retains out-of-page selection after filtering, does not choose a replacement', async () => {
    mount(<WorkPage />);
    await screen.findByRole('heading', { name: work.data.title });
    fireEvent.change(screen.getByLabelText('Kind filter'), {
      target: { value: 'story' },
    });
    await waitFor(() =>
      expect(screen.getByLabelText('Location').textContent).toContain(
        'selected=T-0001',
      ),
    );
    expect(screen.getByRole('heading', { name: work.data.title })).toBeTruthy();
  });
  it('valid unfamiliar IDs reach backend while malformed and historical links never read records', async () => {
    const mounted = mount(<WorkPage />, '/work?selected=FutureNamespace-009');
    await screen.findByText('Not found (404)');
    expect(
      mounted.paths.some((p) => p.endsWith('/work/FutureNamespace-009')),
    ).toBe(true);
    mounted.rendered.unmount();
    mounted.client.clear();
    const malformed = mount(<WorkPage />, '/work?selected=%3Cbad%3E');
    await screen.findByText(/Locally malformed identifier/);
    expect(malformed.paths.some((p) => p.includes('/work/'))).toBe(false);
    malformed.rendered.unmount();
    malformed.client.clear();
    const historic = mount(<WorkPage />, '/work?selected=T-0001&rev=41');
    await screen.findByText(/Historical snapshot reads/);
    expect(historic.paths.some((p) => p.includes('/work'))).toBe(false);
  });
  it('rejects unsupported inspector fields without dependent projection requests', async () => {
    const { paths } = mount(
      <WorkPage />,
      '/work?selected=T-0001&inspector=why&field=secret',
    );
    await screen.findByText(/Unsupported presentation value/);
    expect(paths.some((p) => p.includes('/work'))).toBe(false);
  });
  it('Runs pilot opens supplied invocation details in place', async () => {
    const { paths } = mount(<RunsPage />, '/runs?selected=INV-0001');
    await screen.findByRole('heading', { name: 'Invocation context' });
    expect(paths.some((p) => p.endsWith('/runs/INV-0001'))).toBe(true);
    expect(
      screen.getByRole('region', { name: 'Investigation results' }),
    ).toBeTruthy();
  });
  it('maps reasons, findings and harness status without inventing a binding', () => {
    const target = investigate('work', work.data, source);
    expect(target.explanations[0].bound).toBe(false);
    expect(target.explanations[0].sections[0].name).toBe('blocked_by');
    const invocation = responseSchemas.InvocationResponse.parse(
      f1.responses['/runs/INV-0001'],
    );
    const run = investigate('invocation', invocation.data, {
      value: invocation,
      last_checked_at: source.last_checked_at,
    });
    expect(
      run.explanations.find((e) => e.field.startsWith('runs.'))?.reasons,
    ).toEqual([]);
    const ev = responseSchemas.EvidenceResponse.parse(
      f3.responses['/evidence/INV-0001-verification-1'],
    );
    const evidence = investigate('evidence', ev.data, {
      value: ev,
      last_checked_at: source.last_checked_at,
    });
    expect(evidence.explanations[0].reasons).toEqual([]);
    expect(evidence.explanations[0].sections.map((s) => s.name)).toEqual([
      'findings',
      'deviations',
    ]);
  });
  it('explicit expansion records source fields, terminals, and unknown completeness; list does not crawl', async () => {
    const history = responseSchemas.HistoryResponse.parse(
      f3.responses['/history/T-0004'],
    );
    const root = investigate('history', history.data, {
      value: history,
      last_checked_at: source.last_checked_at,
    });
    const { paths } = mount(
      <RelationsExplorer root={root} />,
      '/history/T-0004',
      f3 as World,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Expand T-0004' }));
    await screen.findByRole('button', {
      name: 'T-0004 · links.tokens · TOKEN-0001',
    });
    expect(
      screen.getByText(/Overall relationship completeness is unknown/),
    ).toBeTruthy();
    const count = paths.length;
    fireEvent.click(screen.getByRole('button', { name: 'Show relation list' }));
    expect(paths.length).toBe(count);
    fireEvent.click(
      screen.getByRole('button', { name: 'T-0004 · links.tokens' }),
    );
    expect(
      screen.getByRole('heading', { name: 'Supplied edge source' }),
    ).toBeTruthy();
    expect(screen.getAllByText(/No edge-specific explanation/).length).toBe(1);
  });
  it('expands hot History dependency and moved-to targets through Work and opens its workspace', async () => {
    const history = responseSchemas.HistoryResponse.parse(
      f3.responses['/history/T-0004'],
    );
    history.data.links.depends_on = ['T-0001'];
    history.data.links.moved_to = ['S-0001'];
    const root = investigate('history', history.data, {
      value: history,
      last_checked_at: source.last_checked_at,
    });
    expect(
      root.relations.find((r) => r.field === 'links.audit_finding')?.target
        .kind,
    ).toBe('history');
    const { paths } = mount(
      <RelationsExplorer root={root} />,
      '/history/T-0004?kind=ticket&cursor=history-page',
      f3 as World,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Expand T-0004' }));
    for (const id of ['T-0001', 'S-0001']) {
      fireEvent.click(
        await screen.findByRole('button', { name: 'Expand ' + id }),
      );
      await waitFor(() => expect(paths).toContain('/api/v1/work/' + id));
    }
    expect(
      paths.some((path) =>
        /^\/api\/v1\/history\/(T-0001|S-0001)(?:\?|$)/.test(path),
      ),
    ).toBe(false);
    const parentLink = screen.getByRole('link', { name: 'S-0001' });
    expect(parentLink.getAttribute('href')).toBe('/work?selected=S-0001');
    fireEvent.click(parentLink);
    expect(screen.getByLabelText('Location').textContent).toBe(
      '/work?selected=S-0001',
    );
    expect(screen.queryByText('Not found (404)')).toBeNull();
  });
  it('graph bounds do not truncate the independently paged supplied relation list', async () => {
    const record = {
      ...work.data,
      children: Array.from({ length: 250 }, (_, i) => 'T-L' + i),
      children_truncated: true,
    };
    const root = investigate('work', record, source);
    mount(<RelationsExplorer root={root} />);
    fireEvent.click(screen.getByRole('button', { name: 'Expand T-0001' }));
    await waitFor(() =>
      expect(document.querySelectorAll('.provenance-node').length).toBe(24),
    );
    expect(screen.getByText(/supplied references omitted/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show relation list' }));
    expect(document.querySelectorAll('.relation-list > li').length).toBe(100);
    fireEvent.click(screen.getByRole('button', { name: 'Next relations' }));
    expect(document.querySelectorAll('.relation-list > li').length).toBe(100);
  });
  it('access refusal clears affected query and transport validator, and does not show cached detail', async () => {
    const { client, request } = mount(<WorkPage />);
    await screen.findByRole('heading', { name: work.data.title });
    request.mockImplementation(async (input) =>
      String(input).endsWith('/work/T-0001')
        ? new Response(null, { status: 403 })
        : new Response(JSON.stringify(f1.responses['/project']), {
            headers: { 'Content-Type': 'application/json' },
          }),
    );
    await client.refetchQueries({
      queryKey: projectionKey('/work/T-0001'),
      exact: true,
    });
    await screen.findByText('Access unavailable (403)');
    expect(screen.queryByRole('heading', { name: work.data.title })).toBeNull();
    expect(client.getQueryData(projectionKey('/work/T-0001'))).toBeUndefined();
  });
  it('null reason messages and unknown semantic fields stay explicit', async () => {
    const r = {
      ...work.data,
      state: 'FUTURE_STATE',
      reasons: [{ code: 'future.reason', message: null }],
    };
    mount(
      <RecordInspection kind="work" record={r} source={source} />,
      '/work?selected=T-0001&inspector=why&field=state',
    );
    await screen.findByRole('heading', { name: /state: FUTURE_STATE/ });
    expect(screen.getByText('No explanation supplied')).toBeTruthy();
    expect(screen.getByText('future.reason')).toBeTruthy();
    expect(screen.getByText('Unknown value:', { exact: false })).toBeTruthy();
  });
});
it('safe dashboard links retain only allowlisted presentation and use accepted opaque ID syntax', () => {
  expect(
    dashboardEntityLink(
      { kind: 'work', id: 'New-Id.003' },
      '?state=READY&secret=hidden',
      true,
    ),
  ).toBe('/work?state=READY&selected=New-Id.003');
  expect(dashboardEntityLink({ kind: 'work', id: '../bad' })).toBeUndefined();
  expect(dashboardEntityLink({ kind: 'unknown', id: 'T-1' })).toBeUndefined();
  expect(
    dashboardCopyLink(
      '/work',
      '?selected=T-1&field=state&cookie=secret&payload=bad',
      'https://local.example',
    ),
  ).toBe('https://local.example/work?selected=T-1&field=state');
});
it('401/403 evicts validators so next request cannot reuse a refused payload', async () => {
  const request = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify(work), {
        headers: { 'Content-Type': 'application/json', ETag: '"old"' },
      }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 403 }))
    .mockResolvedValueOnce(new Response(null, { status: 304 }));
  const client = new ReadTransport(request);
  await client.get('/work/T-0001', responseSchemas.WorkResponse);
  await expect(
    client.get('/work/T-0001', responseSchemas.WorkResponse),
  ).rejects.toBeInstanceOf(ProjectionHttpError);
  await expect(
    client.get('/work/T-0001', responseSchemas.WorkResponse),
  ).rejects.toThrow('304 without');
  expect(
    new Headers(request.mock.calls[2][1].headers).has('If-None-Match'),
  ).toBe(false);
});

it('explicit read-session reset remounts graph and drops an old expansion even when fetch ignores abort', async () => {
  const { useReadSession, resetReadSession } =
    await import('../src/client/queries');
  function Resettable() {
    const session = useReadSession();
    return (
      <>
        <button onClick={() => void resetReadSession()}>
          Reset read session
        </button>
        <InspectorProvider key={session.generation}>
          <WorkPage />
        </InspectorProvider>
      </>
    );
  }
  const { request } = mount(
    <Resettable />,
    '/work?selected=T-0001&inspector=relations',
  );
  await screen.findByRole('button', { name: 'Expand T-0001' });
  fireEvent.click(screen.getByRole('button', { name: 'Expand T-0001' }));
  await screen.findByRole('button', { name: 'Expand S-0001' });
  const original = request.getMockImplementation()!;
  let release: (value: Response) => void = () => {};
  request.mockImplementation((input, init) =>
    String(input).endsWith('/work/S-0001')
      ? new Promise<Response>((resolve) => {
          release = resolve;
        })
      : original(input, init),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Expand S-0001' }));
  await waitFor(() =>
    expect(
      request.mock.calls.some(([input]) =>
        String(input).endsWith('/work/S-0001'),
      ),
    ).toBe(true),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Reset read session' }));
  await waitFor(() =>
    expect(document.querySelectorAll('.provenance-node').length).toBe(1),
  );
  release(
    new Response(
      JSON.stringify({
        ...work,
        data: { ...work.data, id: 'S-0001', children: ['FOREIGN-OLD-CHILD'] },
      }),
      { headers: { 'Content-Type': 'application/json' } },
    ),
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(document.querySelectorAll('.provenance-node').length).toBe(1);
  expect(screen.queryByText('FOREIGN-OLD-CHILD')).toBeNull();
});

it('annotation objects remain untyped references; recognized relation vocabulary does not imply a target type', () => {
  const record = responseSchemas.HistoryResponse.parse(
    f3.responses['/history/T-0004'],
  );
  const root = investigate('history', record.data, {
    value: record,
    last_checked_at: source.last_checked_at,
  });
  expect(
    root.relations
      .filter((r) => r.field.endsWith('.object'))
      .every((r) => r.target.kind === 'reference'),
  ).toBe(true);
  expect(
    dashboardEntityLink({ kind: '__proto__', id: 'T-0001' }),
  ).toBeUndefined();
});
