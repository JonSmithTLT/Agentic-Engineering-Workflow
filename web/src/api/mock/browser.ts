import { http, HttpResponse } from 'msw';
import { setupWorker } from 'msw/browser';
import { selectedWorld } from './worlds';
const checks = new Map<string, number>();
export const worker = setupWorker(
  http.get('/api/v1/*', ({ request }) => {
    const world = selectedWorld();
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname.slice('/api/v1'.length));
    const fault = new URLSearchParams(location.search).get('fault');
    if (world.fixture === 'F10') {
      if (fault === 'offline') return HttpResponse.error();
      if (fault === 'malformed')
        return HttpResponse.json({ bad: 'projection' });
      return new HttpResponse(null, { status: fault === '404' ? 404 : 500 });
    }
    const count = (checks.get(path) ?? 0) + 1;
    checks.set(path, count);
    if (world.fixture === 'F11' && fault === 'refresh-error' && count > 1)
      return new HttpResponse(null, { status: 500 });
    const cursor = url.searchParams.get('cursor');
    let body = cursor ? world.pages[cursor] : world.responses[path];
    if (world.fixture === 'F7' && path === '/history' && cursor) {
      const offset = Number(cursor.split(':').at(-1));
      if (!Number.isInteger(offset) || offset < 0 || offset >= 50000)
        return new HttpResponse(null, { status: 409 });
      const first = world.responses[path] as {
        data: { items: { id: string }[] };
      };
      body = {
        ...first,
        data: {
          items: first.data.items.map((x, i) => ({
            ...x,
            id: `archive/${offset + i}`,
          })),
          next_cursor:
            offset + 100 < 50000 ? `opaque-history:${offset + 100}` : null,
        },
      };
    }
    if (!body) return new HttpResponse(null, { status: 404 });
    const etag = `"${world.fixture}-${path}-${cursor ?? 'first'}"`;
    if (request.headers.get('If-None-Match') === etag)
      return new HttpResponse(null, { status: 304 });
    return HttpResponse.json(body, { headers: { ETag: etag } });
  }),
);
