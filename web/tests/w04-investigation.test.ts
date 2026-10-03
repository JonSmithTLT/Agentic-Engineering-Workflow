import { describe, it, expect } from 'vitest';
import { comparisonSource, packet, packetItem, investigationSchemas, investigationCases, packetBindingIssue, sourceBindingIssue } from '../src/api/preview/investigation/schema';
import { investigationFixture } from '../src/api/preview/investigation/fixtures';
import { InvestigationProjector, investigationBase, investigationEnvelope } from '../src/api/preview/investigation/projector';
import { structuralState, referenceIdentities } from '../src/api/preview/investigation/model';
import { journalFixture } from '../src/api/preview/journal/fixtures';
import { ReadTransport } from '../src/api/transport';
import { RequestLog } from '../src/api/diagnostics';
import { responseSchemas } from '../src/api/schema';
const url = (path: string) => new URL('http://localhost' + investigationBase + path);
describe('W04 supplied context domain', () => {
  it('validates all fixture structures using accepted invocation parsing', () => {
    for (const name of investigationCases) { const fixture = investigationFixture(name); for (const s of fixture.sources) comparisonSource.parse(s); for (const p of fixture.packets) packet.parse(p); for (const i of fixture.items) packetItem.parse(i); }
    const s = investigationFixture().sources[0];
    expect(comparisonSource.safeParse({ ...s, prompt_text: 'secret' }).success).toBe(false);
    expect(comparisonSource.safeParse({ ...s, prompt_id: 'You are an internal agent. Full prompt goes here.' }).success).toBe(false);
    expect(comparisonSource.safeParse({ ...s, invocation: { ...s.invocation, speculative: true } }).success).toBe(false);
    expect(packet.safeParse({ ...investigationFixture().packets[0], raw_prompt: 'secret' }).success).toBe(false);
    expect(packetItem.safeParse({ ...investigationFixture().items[0], artifact_body: 'secret' }).success).toBe(false);
  });
  it('keeps retry context before J-05 publication, and later inclusion separate from benefit', () => {
    const fixture = investigationFixture(), lesson = journalFixture('story').find(j => j.id === 'J-05')!;
    const retry = fixture.packets[1], later = fixture.packets[2];
    expect(Date.parse(retry.prepared_at!)).toBeLessThan(Date.parse(lesson.published_at!));
    expect(fixture.items.filter(i => i.packet_id === retry.id).map(i => i.reference.id)).not.toContain('J-05');
    expect(fixture.items.filter(i => i.packet_id === later.id).map(i => i.reference.id)).toContain('J-05');
    expect(later.receipts.map(r => r.type)).toEqual(['PREPARATION', 'DELIVERY']);
    expect(retry.receipts.some(r => r.type === 'BENEFIT')).toBe(false);
  });
  it('rejects source, packet, receipt and snapshot binding mismatches independently of UI', () => {
    const { sources, packets } = investigationFixture();
    expect(packetBindingIssue(packets[1], sources[1])).toBeUndefined();
    expect(packetBindingIssue(packets[1], sources[0])).toBe('Packet binding mismatch');
    expect(packetBindingIssue({ ...packets[1], snapshot_id: 'OTHER' }, sources[1])).toBe('Packet binding mismatch');
    expect(packetBindingIssue(investigationFixture('malformed').packets[1], sources[1])).toBe('Receipt binding mismatch');
    expect(sourceBindingIssue({ ...sources[0], snapshot_id: null })).toBe('Snapshot binding mismatch');
    expect(sourceBindingIssue({ ...sources[0], packets: [{ ...sources[0].packets[0], run_id: 'OTHER' }] })).toBe('Packet association binding mismatch');
  });
  it('enforces UTF-8 excerpt/page bounds even on otherwise valid structures', () => {
    const item = investigationFixture().items[0];
    const value = (items: unknown[]) => investigationEnvelope({ items, next_cursor: null });
    expect(investigationSchemas.PacketItemListResponse.safeParse(value([{ ...item, excerpt: { format: 'plain', text: 'é'.repeat(8193) } }])).success).toBe(false);
    expect(investigationSchemas.PacketItemListResponse.safeParse(value(Array.from({ length: 9 }, () => ({ ...item, excerpt: { format: 'plain', text: 'a'.repeat(16384) } })))).success).toBe(false);
    expect(investigationSchemas.PacketItemListResponse.safeParse(value([{ ...item, excerpt: { format: 'plain', text: 'a'.repeat(16384) } }])).success).toBe(true);
  });
  it('pages without accumulation, restores opaque cursors across new servers and binds all filters', () => {
    const server = new InvestigationProjector('F1');
    const first = investigationSchemas.ComparisonSourceListResponse.parse(server.read(url('/sources?case=large&limit=50')).body);
    expect(first.data.items).toHaveLength(50);
    expect(first.data.items[0]).not.toHaveProperty('invocation');
    const query = new URLSearchParams({ case: 'large', limit: '50', cursor: first.data.next_cursor! });
    const next = investigationSchemas.ComparisonSourceListResponse.parse(new InvestigationProjector('F1').read(url('/sources?' + query)).body);
    expect(next.data.items).toHaveLength(50); expect(next.data.items[0].id).not.toBe(first.data.items[0].id);
    expect(new InvestigationProjector('F2').read(url('/sources?' + query)).status).toBe(400);
    query.set('work', 'OTHER'); expect(server.read(url('/sources?' + query)).status).toBe(400);
    expect(server.read(url('/sources?limit=51')).status).toBe(400);
    expect(server.read(url('/packets/PKT-Retry?source_id=SRC-Removal')).status).toBe(404);
    const current = investigationSchemas.PacketItemListResponse.parse(server.read(url('/packets/PKT-Retry/items?case=large&source_id=SRC-Retry&section=current')).body);
    expect(current.data.items).toHaveLength(1);
  });
  it('does not expose a denied source payload in its chooser metadata', () => {
    const server = new InvestigationProjector();
    const list = investigationSchemas.ComparisonSourceListResponse.parse(server.read(url('/sources?case=denied')).body);
    expect(list.data.items.find(s => s.id === 'SRC-Retry')).not.toHaveProperty('model_id');
    expect(server.read(url('/sources/SRC-Retry?case=denied')).status).toBe(403);
    expect(server.read(url('/packets/PKT-Retry?case=denied&source_id=SRC-Retry')).status).toBe(403);
  });
  it('compares only complete supplied values, with reference order ignored', () => {
    expect(structuralState(null, null)).toBe('Unavailable');
    expect(structuralState([], [], false)).toBe('Unavailable');
    expect(structuralState('a', 'b')).toBe('Different supplied values');
    expect(structuralState(['Rocky 8', 'clangd 19'], ['clangd 19', 'Rocky 8'])).toBe('Same supplied value');
    expect(structuralState({ kind: 'work', id: 'T-1', title: 'Old title' }, { kind: 'work', id: 'T-1', title: 'New title' })).toBe('Same supplied value');
    expect(structuralState({ format: 'plain', text: 'same' }, { format: 'markdown', text: 'same' })).toBe('Same supplied value');
    expect(referenceIdentities([{ kind: 'x', id: '1' }, { kind: 'y', id: '2' }])).toEqual(referenceIdentities([{ kind: 'y', id: '2' }, { kind: 'x', id: '1' }]));
  });
  it('isolates preview validators, preserves 304 metadata and refuses obsolete responses', async () => {
    const server = new InvestigationProjector(), seen: string[] = [];
    const request = async (input: RequestInfo | URL, init?: RequestInit) => { seen.push(new Headers(init?.headers).get('If-None-Match') ?? 'none'); const result = server.read(new URL('http://localhost' + input)); return seen.length === 2 ? new Response(null, { status: 304, headers: { ETag: '"preview-a"' } }) : Response.json(result.body, { headers: { ETag: '"preview-a"' } }); };
    const reader = new ReadTransport(request, () => new Date(), new RequestLog(), { base: investigationBase, routes: /^\/sources/ }); reader.context.bind('aew-demo');
    const first = await reader.get('/sources/SRC-Removal', investigationSchemas.ComparisonSourceResponse), second = await reader.get('/sources/SRC-Removal', investigationSchemas.ComparisonSourceResponse);
    expect(seen).toEqual(['none', '"preview-a"']); expect(second.value).toBe(first.value);
    let release!: (value: Response) => void;
    const pending = new ReadTransport(() => new Promise(resolve => release = resolve), () => new Date(), new RequestLog(), { base: investigationBase, routes: /^\/sources/ }); pending.context.bind('aew-demo');
    const old = pending.get('/sources/SRC-Removal', investigationSchemas.ComparisonSourceResponse); pending.reset(); release(Response.json(investigationEnvelope(investigationFixture().sources[0])));
    await expect(old).rejects.toMatchObject({ name: 'AbortError' });
    expect(responseSchemas.InvocationResponse.safeParse(first.value).success).toBe(false);
  });
});
