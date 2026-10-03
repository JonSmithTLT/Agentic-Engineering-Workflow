import { describe, expect, it } from 'vitest';
import { webcrypto } from 'node:crypto';
import {
  DemoProjector,
  representationTag,
} from '../src/api/mock/projector';
import type { World } from '../src/api/mock/types';
import f3 from '../src/api/mock/fixtures/F3.json';
import f6 from '../src/api/mock/fixtures/F6.json';
import f7 from '../src/api/mock/fixtures/F7.json';
import f1 from '../src/api/mock/fixtures/F1.json';
import { responseSchemas } from '../src/api/schema';
const url = (route: string) =>
  new URL('/api/v1' + route, 'http://localhost');
function list(server: DemoProjector, route: string) {
  const result = server.read(url(route));
  expect(result.status).toBe(200);
  return result.body as {
    control_revision: string;
    data: { items: Record<string, unknown>[]; next_cursor: string | null };
  };
}
describe('amended C0 demo server behavior (not Engine integration)', () => {
  it('default work exposes hot work plus only the recent 20; archived lookup and explicit terminal filters expose older work', () => {
    const server = new DemoProjector(f3 as World);
    const current = list(server, '/work');
    expect(current.data.items.filter((x) => x.archived)).toHaveLength(20);
    expect(
      current.data.items.find((x) => x.id === 'T-0028'),
    ).toBeUndefined();
    const finished = list(server, '/work?state=DONE');
    expect(finished.data.items.some((x) => x.id === 'T-0028')).toBe(true);
    expect(
      finished.data.items.every((x) => x.archived && x.state === 'DONE'),
    ).toBe(true);
    expect(server.read(url('/work/T-0028')).status).toBe(200);
    expect(
      list(server, '/work?kind=ticket&parent=S-0001').data.items.every(
        (x) => x.kind === 'ticket' && x.parent_id === 'S-0001',
      ),
    ).toBe(true);
    expect(list(server, '/evidence?work=T-0001').data.items).toHaveLength(
      1,
    );
    expect(list(server, '/evidence?work=T-9999').data.items).toHaveLength(
      0,
    );
  });
  it('pages the active frontier within bounds and expires hot cursors on revision changes', () => {
    const server = new DemoProjector(f6 as World);
    const first = list(server, '/work?limit=50');
    expect(first.data.items).toHaveLength(50);
    expect(list(server, '/work?limit=50').data.next_cursor).toBe(
      first.data.next_cursor,
    );
    const token = first.data.next_cursor!;
    const second = list(server, '/work?limit=50&cursor=' + token);
    expect(second.data.items[0].id).toBe('T-1050');
    expect(server.read(url('/work?limit=100&cursor=' + token)).status).toBe(
      400,
    );
    expect(
      server.read(url('/work?limit=50&state=DONE&cursor=' + token)).status,
    ).toBe(400);
    server.changeRevision('43');
    expect(server.read(url('/work?limit=50&cursor=' + token)).status).toBe(
      409,
    );
    expect(server.read(url('/work?limit=251')).status).toBe(400);
    expect(server.read(url('/work?cursor=unissued')).status).toBe(400);
  });
  it('history cursor retains starting count despite appends and control revision changes', () => {
    const server = new DemoProjector(f7 as World);
    const first = list(server, '/history?limit=250');
    server.appendHistory(2);
    server.changeRevision('43');
    let page = first,
      pages = 1;
    const ids = new Set(page.data.items.map((x) => x.id));
    while (page.data.next_cursor) {
      page = list(
        server,
        '/history?limit=250&cursor=' + page.data.next_cursor,
      );
      expect(
        responseSchemas.HistoryListResponse.safeParse(page).success,
      ).toBe(true);
      for (const item of page.data.items) {
        expect(ids.has(item.id)).toBe(false);
        ids.add(item.id);
      }
      pages++;
    }
    expect(pages).toBe(200);
    expect(ids.size).toBe(50000);
    expect(page.data.items.at(-1)?.seq).toBe(50000);
    const fresh = list(server, '/history?limit=250');
    let tail = fresh;
    while (tail.data.next_cursor)
      tail = list(
        server,
        '/history?limit=250&cursor=' + tail.data.next_cursor,
      );
    expect(tail.data.items.map((x) => x.seq)).toEqual([50001, 50002]);
    expect(
      server.read(
        url(
          '/history?kind=audit&limit=250&cursor=' + first.data.next_cursor,
        ),
      ).status,
    ).toBe(400);
    expect(list(server, '/history?kind=audit').data.items).toEqual([]);
    expect(
      list(server, '/history?since=2026-10-03T00:00:00Z').data.items,
    ).toEqual([]);
    expect(
      list(server, '/history?until=2026-10-01T00:00:00Z').data.items,
    ).toEqual([]);
  });
  it('bounds annotation details with scope-bound cursors that survive revision changes', () => {
    const server = new DemoProjector(f3 as World);
    const first = responseSchemas.HistoryResponse.parse(
      server.read(url('/history/T-0004?annotations_limit=1')).body,
    );
    expect(first.data.annotations).toHaveLength(1);
    const token = first.data.annotations_next_cursor;
    server.changeRevision('43');
    server.appendHistory(1);
    const second = responseSchemas.HistoryResponse.parse(
      server.read(
        url(
          '/history/T-0004?annotations_limit=1&annotations_cursor=' + token,
        ),
      ).body,
    );
    expect(second.data.annotations[0].rel).toBe('lineage');
    expect(second.data.annotations_next_cursor).toBeNull();
    expect(
      server.read(
        url(
          '/history/T-0004?annotations_limit=2&annotations_cursor=' + token,
        ),
      ).status,
    ).toBe(400);
  });
  it('ETags distinguish query variants and observed telemetry at unchanged control revision', async () => {
    // Use Node's actual Web Crypto rather than jsdom's incomplete crypto shim.
    const original = globalThis.crypto;
    Object.defineProperty(globalThis, 'crypto', {
      value: webcrypto,
      configurable: true,
    });
    try {
      const body = f1.responses['/runs'];
      const tag = await representationTag(url('/runs'), body);
      expect(await representationTag(url('/runs'), body)).toBe(tag);
      expect(await representationTag(url('/runs?limit=1'), body)).not.toBe(
        tag,
      );
      const changed = structuredClone(body);
      changed.data.items[0].runs[0].status = 'terminated';
      expect(changed.control_revision).toBe(body.control_revision);
      expect(await representationTag(url('/runs'), changed)).not.toBe(tag);
    } finally {
      Object.defineProperty(globalThis, 'crypto', {
        value: original,
        configurable: true,
      });
    }
  });
});
