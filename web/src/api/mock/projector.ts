/** Demo server only. Cursor state and filtering never enter the production client. */
import type { World } from './types';
type Item = Record<string, unknown>;
type Envelope = {
  control_revision: string;
  data: { items: Item[]; next_cursor: string | null };
  [key: string]: unknown;
};
type CursorState = {
  scope: string;
  offset: number;
  revision: string;
  count: number;
};
export class DemoProjector {
  private cursors = new Map<string, CursorState>();
  private serial = 0;
  private tokensByState = new Map<string, string>();
  private appends = 0;
  private revision?: string;
  constructor(private world: World) {}
  appendHistory(count = 1) {
    this.appends += count;
  }
  changeRevision(revision: string) {
    this.revision = revision;
  }
  private issueCursor(state: CursorState) {
    const key = JSON.stringify(state);
    const existing = this.tokensByState.get(key);
    if (existing) return existing;
    const token = `demo-cursor-${++this.serial}`;
    this.tokensByState.set(key, token);
    this.cursors.set(token, state);
    return token;
  }
  read(url: URL): { status: number; body?: unknown } {
    const path = decodeURIComponent(url.pathname.slice('/api/v1'.length));
    const projection =
      path === '/history/integrity'
        ? 'integrity'
        : path.split('/')[1] === 'attention'
          ? 'action_projection'
          : path.split('/')[1];
    const capabilities = this.world.responses['/capabilities'] as {
      data: Record<string, { state: string }>;
    };
    if (
      !['project', 'capabilities'].includes(projection) &&
      (projection in capabilities.data || projection === 'history') &&
      capabilities.data[projection]?.state !== 'AVAILABLE'
    )
      return { status: 403 };
    let original = this.world.responses[path];
    if (!original && path.startsWith('/work/')) {
      const wanted = path.slice('/work/'.length);
      const first = this.world.responses['/work'] as Envelope;
      for (const page of [
        first,
        ...Object.values(this.world.pages),
      ] as Envelope[]) {
        const item = page.data.items.find((x) => x.id === wanted);
        if (item) {
          original = { ...first, data: item };
          break;
        }
      }
    }
    if (
      !original &&
      path.startsWith('/history/') &&
      this.world.fixture === 'F7'
    ) {
      const match = /^\/history\/T-H([0-9]{6})$/.exec(path);
      const seq = match ? Number(match[1]) : 0;
      if (seq > 0 && seq <= 50000 + this.appends) {
        const first = this.world.responses['/history'] as Envelope;
        original = {
          ...first,
          data: {
            ...first.data.items[0],
            id: path.slice('/history/'.length),
            seq,
            annotations: [],
            annotations_next_cursor: null,
          },
        };
      }
    }
    const isList = [
      'work',
      'runs',
      'evidence',
      'knowledge',
      'history',
      'attention',
      'activity',
    ].some((x) => path === `/${x}`);
    if (
      !isList &&
      path !== '/history/integrity' &&
      path.startsWith('/history/') &&
      original
    ) {
      const detail = original as {
        control_revision: string;
        data: { annotations: Item[]; [key: string]: unknown };
      };
      const limit = Number(url.searchParams.get('annotations_limit') ?? 100);
      if (!Number.isInteger(limit) || limit < 1 || limit > 250)
        return { status: 400 };
      const scope = JSON.stringify([path, limit]);
      const token = url.searchParams.get('annotations_cursor');
      const prior = token ? this.cursors.get(token) : undefined;
      if (token && (!prior || prior.scope !== scope)) return { status: 400 };
      const count = prior?.count ?? detail.data.annotations.length;
      const offset = prior?.offset ?? 0;
      const annotations = detail.data.annotations.slice(
        offset,
        Math.min(offset + limit, count),
      );
      const next = offset + annotations.length;
      const annotations_next_cursor =
        next < count
          ? this.issueCursor({
              scope,
              offset: next,
              revision: detail.control_revision,
              count,
            })
          : null;
      return {
        status: 200,
        body: {
          ...detail,
          data: { ...detail.data, annotations, annotations_next_cursor },
        },
      };
    }
    if (!isList)
      return original ? { status: 200, body: original } : { status: 404 };
    const first = original as Envelope;
    for (const key of ['since', 'until']) {
      const value = url.searchParams.get(key);
      if (value && !Number.isFinite(Date.parse(value))) return { status: 400 };
    }
    const limit = Number(url.searchParams.get('limit') ?? 100);
    if (!Number.isInteger(limit) || limit < 1 || limit > 250)
      return { status: 400 };
    const filters = Object.fromEntries(
      [...url.searchParams].filter(([key]) => key !== 'cursor'),
    );
    const scope = JSON.stringify([
      path,
      Object.entries({ ...filters, limit: String(limit) }).sort(),
    ]);
    const revision = this.revision ?? first.control_revision;
    const token = url.searchParams.get('cursor');
    const prior = token ? this.cursors.get(token) : undefined;
    if (token && (!prior || prior.scope !== scope)) return { status: 400 };
    if (prior && path !== '/history' && prior.revision !== revision)
      return { status: 409 };
    let items = first.data.items;
    if (path === '/work') {
      const unique = new Map<string, Item>();
      for (const payload of [
        first,
        ...Object.values(this.world.pages),
      ] as Envelope[])
        for (const item of payload.data.items)
          unique.set(String(item.id), item);
      for (const [route, payload] of Object.entries(this.world.responses))
        if (route.startsWith('/work/')) {
          const item = (payload as { data: Item }).data;
          unique.set(String(item.id), item);
        }
      items = [...unique.values()];
      const state = url.searchParams.get('state');
      const recent = (
        this.world.responses['/overview'] as { data: { recent: Item[] } }
      ).data.recent;
      const recentIds = new Set(recent.map((x) => x.id));
      items = items.filter((x) =>
        state ? x.state === state : !x.archived || recentIds.has(x.id),
      );
      for (const [parameter, field] of [
        ['kind', 'kind'],
        ['parent', 'parent_id'],
      ]) {
        const value = url.searchParams.get(parameter);
        if (value) items = items.filter((x) => x[field] === value);
      }
    }
    if (path === '/evidence') {
      const work = url.searchParams.get('work');
      if (work) items = items.filter((x) => (x.subject as Item).id === work);
    }
    const history = path === '/history';
    const generated = history && this.world.fixture === 'F7';
    const count =
      prior?.count ?? (generated ? 50000 + this.appends : items.length);
    const result: Item[] = [];
    let offset = prior?.offset ?? 0;
    while (offset < count && result.length < limit) {
      const item = generated
        ? {
            ...items[0],
            seq: offset + 1,
            id: `T-H${String(offset + 1).padStart(6, '0')}`,
          }
        : items[offset];
      offset++;
      if (history) {
        const kind = url.searchParams.get('kind'),
          since = url.searchParams.get('since'),
          until = url.searchParams.get('until');
        if (
          (kind && item.kind !== kind) ||
          (since && Date.parse(String(item.at)) < Date.parse(since)) ||
          (until && Date.parse(String(item.at)) > Date.parse(until))
        )
          continue;
      }
      result.push(item);
    }
    let next_cursor: string | null = null;
    if (offset < count) {
      next_cursor = this.issueCursor({ scope, offset, revision, count });
    }
    return {
      status: 200,
      body: {
        ...first,
        control_revision: revision,
        data: { items: result, next_cursor },
      },
    };
  }
}
/** Includes filters, limits, payload and telemetry even when control_revision is unchanged. */
export async function representationTag(url: URL, body: unknown) {
  const normalized = new URL(url);
  normalized.searchParams.sort();
  const bytes = new TextEncoder().encode(
    JSON.stringify([normalized.pathname, normalized.search, body]),
  );
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return `"${Array.from(new Uint8Array(digest), (x) => x.toString(16).padStart(2, '0')).join('')}"`;
}
