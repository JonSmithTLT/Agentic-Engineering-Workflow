import fs from 'node:fs';
import { createHash } from 'node:crypto';
import {
  act,
  render,
  screen,
  fireEvent,
  waitFor,
} from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { acceptedContract } from '../src/api/registry';
import {
  scenarioConfig,
  generatedScenarioSchema,
} from '../src/api/mock/lab/config';
import {
  recipes,
  readScenario,
  scenarioLink,
} from '../src/api/mock/lab/catalog';
import { ReplayEngine } from '../src/api/mock/lab/engine';
import { validateInput } from '../src/api/mock/lab/validation';
import { responseSchemas } from '../src/api/schema';
import { DashboardProvider } from '../src/client/dashboard';
import { queryClient, projectionKey } from '../src/client/queries';
import { transport } from '../src/api/transport';
import { WorkPage } from '../src/pages/Work';
import f1 from '../src/api/mock/fixtures/F1.json';
import type { World } from '../src/api/mock/types';
import { DeveloperPanel } from '../src/components/DeveloperPanel';
it('registry retains accepted identity and preview guidance requires explicit absent explanations', () => {
  expect(acceptedContract.version).toBe('0.1.2');
  expect(acceptedContract.disposition).toBe('ACCEPTED');
  expect(acceptedContract.parsers.WorkResponse).toBe(
    responseSchemas.WorkResponse,
  );
  expect(acceptedContract.fixtures).toHaveLength(12);
  const guidance = fs.readFileSync('src/api/preview/README.md', 'utf8');
  expect(guidance).toContain('no\nexplanation supplied');
  expect(guidance).toContain('may not synthesize');
});
it('generated scenario schema and manifest match runtime and links restart without payloads', () => {
  const text = JSON.stringify(generatedScenarioSchema(), null, 2) + '\n';
  expect(
    fs.readFileSync('docs/design/scenario-config.schema.json', 'utf8'),
  ).toBe(text);
  expect(
    JSON.parse(
      fs.readFileSync('docs/design/scenario-config.manifest.json', 'utf8'),
    ).sha256,
  ).toBe(createHash('sha256').update(text).digest('hex'));
  const link = scenarioLink(
    recipes[0],
    17,
    'http://localhost/work?cursor=private&step=3',
  );
  const config = readScenario(new URL(link).search)!;
  expect(config.seed).toBe(17);
  expect(link).not.toContain('cursor');
  expect(link).not.toContain('step');
  expect(
    scenarioConfig.safeParse({ ...config, definition: undefined }).success,
  ).toBe(false);
  expect(
    readScenario('?catalog=99&recipe=conditional&fixture=F1&seed=1'),
  ).toBeUndefined();
});
it('contract validation separates syntax, shape, future semantics and bounded input', () => {
  expect(validateInput('WorkResponse', '{').status).toBe('Invalid JSON');
  const malformed = validateInput(
    'WorkResponse',
    JSON.stringify({ bad: true }),
  );
  expect(malformed.status).toBe('Invalid shape');
  expect(malformed.issues.some((i) => i.field === 'project_id')).toBe(true);
  const work = structuredClone(f1.responses['/work/T-0001']);
  work.data.state = 'FUTURE';
  const future = validateInput('WorkResponse', JSON.stringify(work));
  expect(future.status).toContain('unknown semantic');
  expect(future.issues[0].field).toBe('data.state');
  expect(
    validateInput('WorkResponse', 'x'.repeat(256 * 1024 + 1)).status,
  ).toContain('256 KiB');
});
it('developer tabs support keyboard selection, only demo mounts its lab, Escape closes', () => {
  const close = vi.fn();
  function Demo({ tab }: { tab: string }) {
    return <div role="tabpanel">Demo {tab}</div>;
  }
  const view = render(<DeveloperPanel close={close} demoLab={Demo} />);
  fireEvent.keyDown(screen.getByRole('tab', { name: 'Requests' }), {
    key: 'ArrowRight',
  });
  expect(
    screen
      .getByRole('tab', { name: 'Scenarios' })
      .getAttribute('aria-selected'),
  ).toBe('true');
  expect(screen.getByText('Demo Scenarios')).toBeTruthy();
  fireEvent.keyDown(screen.getByLabelText('API developer panel'), {
    key: 'Escape',
  });
  expect(close).toHaveBeenCalled();
  view.rerender(<DeveloperPanel close={close} />);
  expect(screen.queryByRole('tab')).toBeNull();
});
async function mountRecipe(id: string) {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: 'visible',
  });
  queryClient.clear();
  const recipe = recipes.find((r) => r.id === id)!;
  const engine = new ReplayEngine(recipe, 17, f1 as World);
  await engine.start();
  const calls: Request[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const request = new Request(
      new URL(String(input), 'http://localhost'),
      init,
    );
    calls.push(request);
    const result = await engine.respond(request);
    if (result.network) throw new TypeError('Network request failed');
    return new Response(
      result.status === 200 ? JSON.stringify(result.body) : null,
      {
        status: result.status,
        headers: {
          'Content-Type': 'application/json',
          ...(result.etag ? { ETag: result.etag } : {}),
        },
      },
    );
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardProvider>
          <WorkPage />
        </DashboardProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(
      queryClient
        .getQueryCache()
        .findAll({ type: 'active' })
        .some((q) => q.state.fetchStatus === 'fetching'),
    ).toBe(false),
  );
  const next = async () => {
    await act(async () => {
      await engine.next();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  };
  const close = () => {
    view.unmount();
    queryClient.clear();
  };
  return { engine, next, calls, close };
}
it('composed replay conditional 304 preserves generation and malformed refresh preserves cached content', async () => {
  const probe = await mountRecipe('failed-refresh');
  await screen.findByRole('heading', { name: 'Work records' });
  const key = projectionKey('/overview');
  const first = queryClient.getQueryData(key);
  await probe.next();
  await screen.findByText('STALE / DISCONNECTED');
  await probe.next();
  expect((queryClient.getQueryData(key) as { value: unknown }).value).toBe(
    (first as { value: unknown }).value,
  );
  await probe.next();
  await screen.findByText('CURRENT');
  probe.close();
});
it('manual visible divergence pauses hidden and clears on convergence', async () => {
  const probe = await mountRecipe('persistent-mixed');
  await screen.findByRole('heading', { name: 'Work records' });
  await probe.next();
  await screen.findByText('UPDATING');
  for (let i = 1; i < 5; i++) await probe.next();
  expect(screen.getByText('UPDATING')).toBeTruthy();
  expect(screen.queryByText(/Mixed revisions persist/)).toBeNull();
  await probe.next();
  await screen.findByText(/Mixed revisions persist/);
  await probe.next();
  await screen.findByText('CURRENT');
  probe.close();
});
it('capability downgrade suppresses subsequent Work reads and excludes hidden cached revision', async () => {
  const probe = await mountRecipe('capability');
  await screen.findByRole('heading', { name: 'Work records' });
  await probe.next();
  await screen.findByText(/Authored fixture downgrade/);
  const count = probe.calls.filter(
    (r) => new URL(r.url).pathname === '/api/v1/work',
  ).length;
  await probe.next();
  expect(
    probe.calls.filter((r) => new URL(r.url).pathname === '/api/v1/work'),
  ).toHaveLength(count);
  probe.close();
});
it('late ignored-cancellation response cannot enter the new session after replay switch', async () => {
  const probe = await mountRecipe('late-session');
  await screen.findByRole('heading', { name: 'Work records' });
  await probe.next();
  await waitFor(() => expect(probe.engine.state.pending).toHaveLength(1));
  const held = probe.engine.state.pending[0];
  const old = transport.context.generation;
  await probe.next();
  await waitFor(() =>
    expect(transport.context.projectId).toBe('demo-aew-other'),
  );
  expect(transport.context.generation).not.toBe(old);
  await act(async () => {
    probe.engine.release(held.id);
    await Promise.resolve();
  });
  const all = queryClient
    .getQueryCache()
    .findAll()
    .flatMap((q) =>
      q.state.data ? [q.state.data as { value: { project_id: string } }] : [],
    );
  expect(all.every((p) => p.value.project_id === 'demo-aew-other')).toBe(true);
  probe.close();
});
it('reset replay reproduces the same logical sequence and diagnoses extra ordinal requests', async () => {
  const recipe = recipes.find((r) => r.id === 'conditional')!;
  const engine = new ReplayEngine(recipe, 17, f1 as World);
  await engine.start();
  const request = new Request('http://localhost/api/v1/project');
  await engine.respond(request);
  const sequence = [...engine.state.events];
  await engine.reset();
  await engine.respond(request);
  expect(engine.state.events).toEqual(sequence);
  await engine.respond(request);
  expect(engine.state.diagnostics[0]).toContain('Unmatched harness request');
  queryClient.clear();
});
