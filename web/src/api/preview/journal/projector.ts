import { journalFixture } from './fixtures';
import { journalCases, type JournalEntry } from './schema';
export const previewBase = '/api/preview/journal/v0.1';
export function comparePublished(a: JournalEntry, b: JournalEntry) {
    if (a.published_at === null && b.published_at !== null)
        return 1;
    if (b.published_at === null && a.published_at !== null)
        return -1;
    const time = (b.published_at ? Date.parse(b.published_at) : 0) - (a.published_at ? Date.parse(a.published_at) : 0);
    return time || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
}
export function journalEnvelope<T>(data: T, project = 'aew-demo', revision = '42') {
    return { schema_version: '0.1.0' as const, project_id: project, control_revision: revision, generated_at: '2026-10-03T12:00:00Z', data };
}
/** Only the demo server filters/orders. The client renders the supplied page. */
export class JournalProjector {
    private cursors = new Map<string, {
        scope: string;
        offset: number;
    }>();
    private serial = 0;
    read(url: URL, project = 'aew-demo', revision = '42'): {
        status: number;
        body?: unknown;
    } {
        const p = url.searchParams, name = p.get('case') ?? 'story';
        if (!journalCases.includes(name as typeof journalCases[number]))
            return { status: 400 };
        if (name === 'denied')
            return { status: 403 };
        if (name === 'not-found')
            return { status: 404 };
        if (name === 'malformed')
            return { status: 200, body: { raw_prompt: 'invalid demonstration' } };
        const records = journalFixture(name), route = url.pathname.slice(previewBase.length);
        if (route.startsWith('/entries/')) {
            const id = decodeURIComponent(route.slice('/entries/'.length));
            const entry = records.find((r) => r.id === id);
            return entry ? { status: 200, body: journalEnvelope(entry, project, revision) } : { status: 404 };
        }
        if (route !== '/entries' || p.get('limit') !== '50')
            return { status: 400 };
        const components = [...new Set(records.flatMap((r) => r.component === null ? [] : [r.component]))].sort();
        const kinds = [...new Set(records.map((r) => r.kind))].sort();
        const component = p.get('component'), missing = p.get('component_missing'), kind = p.get('kind');
        if (component && missing)
            return { status: 400 };
        const filtered = records.filter((r) => (!kind || r.kind === kind) && (!component || r.component === component) && (!missing || r.component === null)).sort(comparePublished);
        const scope = JSON.stringify([name, project, revision, component, missing, kind]);
        const token = p.get('cursor'), cursor = token ? this.cursors.get(token) : undefined;
        if (token && (!cursor || cursor.scope !== scope))
            return { status: 400 };
        const offset = cursor?.offset ?? 0;
        let next: string | null = null;
        if (offset + 50 < filtered.length) {
            const existing = [...this.cursors].find(([, c]) => c.scope === scope && c.offset === offset + 50);
            next = existing?.[0] ?? `journal-cursor-${++this.serial}`;
            this.cursors.set(next, { scope, offset: offset + 50 });
        }
        return { status: 200, body: journalEnvelope({ items: filtered.slice(offset, offset + 50), next_cursor: next, components, kinds }, project, revision) };
    }
}
