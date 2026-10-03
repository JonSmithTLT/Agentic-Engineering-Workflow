import { ReplayEngine } from './lab/engine';
import { readScenario } from './lab/catalog';
import { worlds } from './worlds';
import { http, HttpResponse } from 'msw';
import { setupWorker } from 'msw/browser';
import { journalHandlers } from '../preview/journal/handlers';
import { selectedWorld } from './worlds';
import { DemoProjector, representationTag } from './projector';
const scenario = readScenario(location.search);
export const replay = scenario
  ? new ReplayEngine(
      scenario.definition,
      scenario.seed,
      worlds.find((w) => w.fixture === scenario.fixture)!,
    )
  : undefined;
export async function initializeDemo() {
  if (replay) await replay.start();
  else {
    const { transport } = await import('../transport');
    transport.reset({
      ...transport.context.identity,
      mode: 'demo',
      dataset: selectedWorld().fixture,
    });
  }
}
const checks = new Map<string, number>();
const servers = new Map<string, DemoProjector>();
async function respond({ request }: { request: Request }) {
  if (replay) {
    const result = await replay.respond(request);
    if (result.network) return HttpResponse.error();
    if (result.status !== 200)
      return new HttpResponse(null, {
        status: result.status,
        headers: result.etag ? { ETag: result.etag } : {},
      });
    return request.method === 'HEAD'
      ? new HttpResponse(null, {
          headers: result.etag ? { ETag: result.etag } : {},
        })
      : new HttpResponse(JSON.stringify(result.body), {
          headers: {
            'Content-Type': 'application/json',
            ...(result.etag ? { ETag: result.etag } : {}),
          },
        });
  }
  const world = selectedWorld();
  const url = new URL(request.url);
  const fault = new URLSearchParams(location.search).get('fault');
  if (world.fixture === 'F10') {
    if (fault === 'offline') return HttpResponse.error();
    if (fault === 'malformed') return HttpResponse.json({ bad: 'projection' });
    return new HttpResponse(null, { status: fault === '404' ? 404 : 500 });
  }
  const count = (checks.get(url.pathname) ?? 0) + 1;
  checks.set(url.pathname, count);
  if (world.fixture === 'F11' && fault === 'refresh-error' && count > 1)
    return new HttpResponse(null, { status: 500 });
  let server = servers.get(world.fixture);
  if (!server) {
    server = new DemoProjector(world);
    servers.set(world.fixture, server);
  }
  const result = server.read(url);
  if (result.status !== 200)
    return new HttpResponse(null, { status: result.status });
  const etag = await representationTag(url, result.body);
  if (request.headers.get('If-None-Match') === etag)
    return new HttpResponse(null, { status: 304, headers: { ETag: etag } });
  return request.method === 'HEAD'
    ? new HttpResponse(null, { headers: { ETag: etag } })
    : new HttpResponse(JSON.stringify(result.body), {
        headers: { ETag: etag, 'Content-Type': 'application/json' },
      });
}
export const worker = setupWorker(
  ...journalHandlers,
  http.get('/api/v1/*', respond),
  http.head('/api/v1/*', respond),
);
