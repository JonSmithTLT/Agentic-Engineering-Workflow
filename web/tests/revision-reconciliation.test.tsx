import { act, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { DashboardProvider, PageSnapshot } from '../src/client/dashboard';
import { installVisibility, useProjection } from '../src/client/queries';
import { ReadTransport, transport } from '../src/api/transport';
import { responseSchemas } from '../src/api/schema';
import { DemoProjector } from '../src/api/mock/projector';
import f1 from '../src/api/mock/fixtures/F1.json';
import type { World } from '../src/api/mock/types';
function visibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: state,
  });
  document.dispatchEvent(new Event('visibilitychange'));
}
function setup(stuckProject = false) {
  visibility('visible');
  vi.useFakeTimers();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const server = new DemoProjector(f1 as World);
  let revision = 42n;
  const request = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost');
      const result = server.read(url);
      const value = structuredClone(result.body) as {
        control_revision: string;
        generated_at: string;
      };
      const rev =
        stuckProject && url.pathname === '/api/v1/project' ? 42n : revision;
      value.control_revision = String(rev);
      const etag = `"${url.pathname}-${rev}"`;
      if (new Headers(init?.headers).get('If-None-Match') === etag)
        return new Response(null, { status: 304, headers: { ETag: etag } });
      return new Response(JSON.stringify(value), {
        headers: { 'Content-Type': 'application/json', ETag: etag },
      });
    },
  );
  const scoped = new ReadTransport(request);
  vi.spyOn(transport, 'get').mockImplementation((route, schema, signal) =>
    scoped.get(route, schema, signal),
  );
  const dispose = installVisibility(client);
  function Probe() {
    const detail = useProjection(
      '/work/T-0001',
      responseSchemas.WorkResponse,
      'detail',
    );
    const history = useProjection(
      '/history?limit=100',
      responseSchemas.HistoryListResponse,
      'history',
    );
    const disabled = useProjection(
      '/knowledge?limit=100',
      responseSchemas.KnowledgeListResponse,
      'history',
      false,
    );
    return <PageSnapshot queries={[detail, history, disabled]} />;
  }
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardProvider>
          <Probe />
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return {
    client,
    request,
    setRevision: (value: bigint) => {
      revision = value;
    },
    advanceRevision: () => {
      revision++;
    },
    close: () => {
      view.unmount();
      dispose();
      client.clear();
    },
  };
}
async function tick(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}
function revisions(client: QueryClient) {
  return client
    .getQueryCache()
    .findAll({ type: 'active', queryKey: ['projection'] })
    .map(
      (q) =>
        (q.state.data as { value?: { control_revision?: string } } | undefined)
          ?.value?.control_revision,
    )
    .filter(Boolean);
}
it('busy revisions every 3s for 60s catch up unequal polling cadences without a persistent warning', async () => {
  const probe = setup();
  await tick(100);
  const timer = setInterval(probe.advanceRevision, 3000);
  try {
    for (let i = 0; i < 20; i++) {
      await tick(3000);
      expect(new Set(revisions(probe.client)).size).toBe(1);
      expect(screen.queryByText(/Mixed revisions persist/)).toBeNull();
    }
    expect(
      probe.request.mock.calls.filter(([url]) =>
        String(url).endsWith('/project'),
      ).length,
    ).toBeGreaterThan(10);
    // Historical collections have no interval, but a newer observed revision revalidates them.
    expect(
      probe.request.mock.calls.filter(([url]) =>
        String(url).includes('/history?'),
      ).length,
    ).toBeGreaterThan(10);
  } finally {
    clearInterval(timer);
    probe.close();
  }
});
it('a genuinely stuck 304 projection still warns after 30 visible seconds without an immediate retry storm', async () => {
  const probe = setup(true);
  await tick(100);
  const timer = setInterval(probe.advanceRevision, 3000);
  try {
    for (let i = 0; i < 20; i++) await tick(3000);
    expect(screen.getByText(/Mixed revisions persist/)).toBeTruthy();
    expect(new Set(revisions(probe.client)).size).toBe(2);
    const calls = probe.request.mock.calls.filter(([url]) =>
      String(url).endsWith('/project'),
    );
    expect(calls.length).toBeLessThan(40);
    expect(
      calls.some(([, init]) => new Headers(init?.headers).has('If-None-Match')),
    ).toBe(true);
  } finally {
    clearInterval(timer);
    probe.close();
  }
});
it('an unchanged high revision causes one immediate catch-up attempt, not a self-refetch loop', async () => {
  const probe = setup(true);
  await tick(100);
  try {
    probe.setRevision(43n);
    await act(async () => {
      await probe.client.refetchQueries({
        queryKey: ['projection', '/overview'],
        exact: true,
      });
    });
    await tick(100);
    const projectCount = () =>
      probe.request.mock.calls.filter(([url]) =>
        String(url).endsWith('/project'),
      ).length;
    expect(projectCount()).toBe(2);
    await tick(5000);
    expect(projectCount()).toBe(2);
  } finally {
    probe.close();
  }
});
it('decimal revisions beyond Number precision are compared numerically and catch up immediately', async () => {
  const probe = setup();
  await tick(100);
  try {
    probe.setRevision(9007199254740992n);
    await act(async () => {
      await probe.client.refetchQueries({
        queryKey: ['projection', '/overview'],
        exact: true,
      });
    });
    await tick(100);
    probe.setRevision(9007199254740993n);
    await act(async () => {
      await probe.client.refetchQueries({
        queryKey: ['projection', '/overview'],
        exact: true,
      });
    });
    await tick(100);
    expect(new Set(revisions(probe.client))).toEqual(
      new Set(['9007199254740993']),
    );
  } finally {
    probe.close();
  }
});
it('hidden, disabled and inactive projections cannot trigger or receive automatic catch-up', async () => {
  const probe = setup();
  await tick(100);
  try {
    const high = {
      value: { ...f1.responses['/project'], control_revision: '1000000' },
      last_checked_at: '2026-10-02T12:00:00Z',
    };
    act(() => {
      probe.client.setQueryData(['projection', '/knowledge?limit=100'], high);
      probe.client.setQueryData(['projection', '/work/T-inactive'], high);
    });
    await tick(50);
    expect(screen.getByText('CURRENT')).toBeTruthy();
    expect(
      probe.request.mock.calls.some(
        ([url]) =>
          String(url).includes('/knowledge') ||
          String(url).includes('T-inactive'),
      ),
    ).toBe(false);
    act(() => visibility('hidden'));
    const count = probe.request.mock.calls.length;
    act(() =>
      probe.client.setQueryData(['projection', '/overview'], {
        value: { ...f1.responses['/overview'], control_revision: '43' },
        last_checked_at: '2026-10-02T12:00:00Z',
      }),
    );
    await tick(30000);
    expect(probe.request).toHaveBeenCalledTimes(count);
    probe.setRevision(43n);
    await act(async () => {
      visibility('visible');
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(new Set(revisions(probe.client))).toEqual(new Set(['43']));
    expect(
      probe.request.mock.calls.some(
        ([url]) =>
          String(url).includes('/knowledge') ||
          String(url).includes('T-inactive'),
      ),
    ).toBe(false);
  } finally {
    visibility('visible');
    probe.close();
  }
});
