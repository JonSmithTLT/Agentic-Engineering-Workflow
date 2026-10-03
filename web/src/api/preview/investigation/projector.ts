import { investigationFixture } from './fixtures';
import { investigationCases, comparisonSource } from './schema';
export const investigationBase = '/api/preview/investigation/v0.1';
export function investigationEnvelope<T>(data: T, project = 'aew-demo', revision = '42') {
  return { schema_version: '0.1.0' as const, project_id: project, control_revision: revision, generated_at: '2026-10-03T12:00:00Z', data };
}
export class InvestigationProjector {
  constructor(private dataset = 'demo', private acceptedInvocations: unknown[] = []) {}
  private counts = new Map<string, number>();
  read(url: URL, project = 'aew-demo', revision = '42'): { status: number; body?: unknown } {
    const p = url.searchParams, name = p.get('case') ?? 'story', route = url.pathname.slice(investigationBase.length);
    if (!investigationCases.includes(name as typeof investigationCases[number])) return { status: 400 };
    const countKey = JSON.stringify([project, revision, url.href]), count = (this.counts.get(countKey) ?? 0) + 1; this.counts.set(countKey, count);
    if ((name === 'refresh-error' || name === 'stale') && route === '/sources/SRC-Retry' && count > 2) return { status: 500 };
    if (name === 'denied' && route !== '/sources' && !route.endsWith('SRC-Removal')) return { status: 403 };
    if ((name === 'not-found' || name === 'historical-unavailable') && route === '/sources/SRC-Retry') return { status: 404 };
    const data = investigationFixture(name);
    if (name === 'story') for (const value of this.acceptedInvocations) {
      const invocation = comparisonSource.shape.invocation.parse(value);
      data.sources.push({ ...structuredClone(data.sources[0]), id: `CURRENT-${invocation.id}`, invocation, mode: 'CURRENT', snapshot_id: null, captured_at: null, visibility_scope: `${this.dataset}-authorized`, work_revision: null, source_revision: null, environment: [], model_id: null, provider: null, profile_id: null, card_id: null, capability_id: null, prompt_id: null, prompt_version: null, prompt_digest: null, evidence_complete: false, packets: [], packets_complete: false });
    }
    if (/^\/sources\/[^/]+$/.test(route)) { const source = data.sources.find(s => s.id === decodeURIComponent(route.slice(9))); return source ? { status: 200, body: investigationEnvelope(source, project, revision) } : { status: 404 }; }
    const match = /^\/packets\/([^/]+)(\/items)?$/.exec(route);
    if (match) {
      const packet = data.packets.find(v => v.id === decodeURIComponent(match[1]));
      if (!p.get('source_id') || !packet || packet.source_id !== p.get('source_id')) return { status: 404 };
      if (!match[2]) return { status: 200, body: investigationEnvelope(packet, project, revision) };
    } else if (route !== '/sources') return { status: 404 };
    const limit = Number(p.get('limit') ?? 50);
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) return { status: 400 };
    const scope = JSON.stringify([this.dataset, project, revision, name, route, p.get('work'), p.get('source_id'), p.get('section'), p.get('disposition'), limit]);
    const token = p.get('cursor');
    let offset = 0;
    if (token) { try { const [bound, position] = JSON.parse(decodeURIComponent(token)); if (token.length > 8192 || bound !== scope || !Number.isInteger(position) || position < 0 || position % limit !== 0) return { status: 400 }; offset = position; } catch { return { status: 400 }; } }
    const rows = match ? data.items.filter(v => v.packet_id === match[1] && v.source_id === p.get('source_id') && (!p.get('section') || v.section === p.get('section')) && (!p.get('disposition') || v.disposition === p.get('disposition'))) : data.sources.filter(s => !p.get('work') || s.invocation.work.id === p.get('work'));
    const sorted = [...rows].sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    let next: string | null = null;
    if (offset > sorted.length) return { status: 400 };
    if (offset + limit < sorted.length) next = encodeURIComponent(JSON.stringify([scope, offset + limit]));
    const page = sorted.slice(offset, offset + limit);
    const items = match ? page : page.map(value => { const s = value as typeof data.sources[number]; const text = name === 'denied' && s.id !== 'SRC-Removal' ? null : s.invocation.summary?.text ?? null; return { id: s.id, invocation_id: s.invocation.id, work: s.invocation.work, summary: text?.slice(0, 512) ?? null, summary_truncated: text !== null && text.length > 512, status: s.invocation.status, mode: s.mode, snapshot_id: s.snapshot_id, captured_at: s.captured_at, visibility_scope: s.visibility_scope }; });
    return { status: 200, body: investigationEnvelope({ items, next_cursor: next }, project, revision) };
  }
}
