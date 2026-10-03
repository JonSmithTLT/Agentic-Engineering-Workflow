import { act, render, screen } from '@testing-library/react';
import {
  QueryClient,
  QueryClientProvider,
  QueryObserver,
} from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { ReadTransport } from '../src/api/transport';
import { ReadContext, liveIdentity } from '../src/api/read-context';
import { responseSchemas } from '../src/api/schema';
import { RequestLog } from '../src/api/diagnostics';
import { DashboardProvider } from '../src/client/dashboard';
import { WorkPage } from '../src/pages/Work';
import { installRevisionReconciliation } from '../src/client/revisions';
import f1 from '../src/api/mock/fixtures/F1.json';
const overview = f1.responses['/overview'];
const project = f1.responses['/project'];
const json = (body: unknown, etag = '"first"') =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json', ETag: etag },
  });
it('isolates payload and validator identity after a dataset/authorization reset', async () => {
  const request = vi
    .fn()
    .mockResolvedValueOnce(json(overview))
    .mockResolvedValueOnce(json({ ...overview, project_id: 'other' }));
  const transport = new ReadTransport(request);
  await transport.get('/overview', responseSchemas.OverviewResponse);
  transport.reset({
    ...liveIdentity,
    dataset: 'other',
    authorization_generation: 'next',
  });
  const second = await transport.get(
    '/overview',
    responseSchemas.OverviewResponse,
  );
  expect(second.value.project_id).toBe('other');
  expect(request.mock.calls[1][1].headers.has('If-None-Match')).toBe(false);
});
for (const status of [200, 304])
  it(`retired late ${status} cannot commit or repopulate diagnostics`, async () => {
    let release!: (r: Response) => void;
    const request = vi
      .fn()
      .mockResolvedValueOnce(json(overview))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            release = resolve;
          }),
      )
      .mockResolvedValueOnce(json(overview, '"new"'));
    const log = new RequestLog();
    const transport = new ReadTransport(request, () => new Date(), log);
    await transport.get('/overview', responseSchemas.OverviewResponse);
    const pending = transport.get(
      '/overview',
      responseSchemas.OverviewResponse,
    );
    const rejected = expect(pending).rejects.toThrow('aborted');
    transport.reset({ ...liveIdentity, authorization_generation: 'retired' });
    release(
      status === 304 ? new Response(null, { status: 304 }) : json(overview),
    );
    await rejected;
    expect(log.snapshot()).toHaveLength(0);
    await transport.get('/overview', responseSchemas.OverviewResponse);
    expect(request.mock.calls[2][1].headers.has('If-None-Match')).toBe(false);
  });
it('binds bootstrap project, rejects foreign envelopes and preserves its own cached payload', async () => {
  const request = vi
    .fn()
    .mockResolvedValueOnce(json(project))
    .mockResolvedValueOnce(json(overview))
    .mockResolvedValueOnce(json({ ...overview, project_id: 'foreign' }))
    .mockResolvedValueOnce(new Response(null, { status: 304 }));
  const transport = new ReadTransport(request);
  await transport.get('/project', responseSchemas.ProjectResponse);
  const first = await transport.get(
    '/overview',
    responseSchemas.OverviewResponse,
  );
  await expect(
    transport.get('/overview', responseSchemas.OverviewResponse),
  ).rejects.toThrow('different project');
  expect(
    (await transport.get('/overview', responseSchemas.OverviewResponse)).value,
  ).toBe(first.value);
});
it('bootstraps project before dependent capabilities and Work requests', async () => {
  const calls: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const route = String(input).replace('/api/v1', '');
    calls.push(route);
    const fixtureRoute = route.startsWith('/work?') ? '/work' : route;
    return json(f1.responses[fixtureRoute as keyof typeof f1.responses]);
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardProvider>
          <WorkPage />
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole('heading', { name: 'Work records' });
  expect(calls[0]).toBe('/project');
  expect(calls.indexOf('/capabilities')).toBeGreaterThan(0);
  view.unmount();
  client.clear();
});
it('revision reconciliation does not cross snapshots or authorization contexts', async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  const a = new ReadContext({ ...liveIdentity, snapshot: 'snapshot-a' }),
    b = new ReadContext({ ...liveIdentity, snapshot: 'snapshot-b' });
  a.bind(project.project_id);
  b.bind(project.project_id);
  const refetch = vi.fn();
  const disposers = [];
  for (const [context, rev] of [
    [a, '1'],
    [b, '100'],
  ] as const) {
    const key = ['projection', context.key('/overview'), '/overview'];
    client.setQueryData(key, {
      value: { project_id: project.project_id, control_revision: rev },
    });
    disposers.push(
      new QueryObserver(client, {
        queryKey: key,
        queryFn: refetch,
        staleTime: Infinity,
      }).subscribe(() => {}),
    );
  }
  const dispose = installRevisionReconciliation(client);
  await act(async () => {
    await Promise.resolve();
  });
  expect(refetch).not.toHaveBeenCalled();
  dispose();
  disposers.forEach((d) => d());
  client.clear();
});

it('different routes in the same context never share validators or 304 payloads', async () => {
  const caps = f1.responses['/capabilities'];
  const request = vi
    .fn()
    .mockResolvedValueOnce(json(project, '"project"'))
    .mockResolvedValueOnce(json(caps, '"caps"'))
    .mockResolvedValueOnce(json(overview, '"overview"'))
    .mockResolvedValueOnce(new Response(null, { status: 304 }));
  const client = new ReadTransport(request);
  await client.get('/project', responseSchemas.ProjectResponse);
  const first = await client.get(
    '/capabilities',
    responseSchemas.CapabilitiesResponse,
  );
  await client.get('/overview', responseSchemas.OverviewResponse);
  expect(request.mock.calls[2][1].headers.has('If-None-Match')).toBe(false);
  const recheck = await client.get(
    '/capabilities',
    responseSchemas.CapabilitiesResponse,
  );
  expect(recheck.value).toBe(first.value);
  expect(request.mock.calls[3][1].headers.get('If-None-Match')).toBe('"caps"');
});
