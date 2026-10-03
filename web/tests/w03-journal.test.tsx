import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DashboardProvider } from '../src/client/dashboard';
import Journal from '../src/api/preview/journal/Journal';
import { journalSchemas, journalEntry } from '../src/api/preview/journal/schema';
import { journalFixture, story } from '../src/api/preview/journal/fixtures';
import { JournalProjector, comparePublished, journalEnvelope } from '../src/api/preview/journal/projector';
import { journalContract } from '../src/api/preview/journal/registration';
import { inspectJournal } from '../src/api/preview/journal/model';
import { ReadTransport } from '../src/api/transport';
import { RequestLog } from '../src/api/diagnostics';
import { transport } from '../src/api/transport';
import { DemoProjector } from '../src/api/mock/projector';
import f1 from '../src/api/mock/fixtures/F1.json';
import type { World } from '../src/api/mock/types';
import { validateInput } from '../src/api/mock/lab/validation';
describe('Journal provisional contract', () => {
    it('validates all authored cases and rejects raw prompts and malformed timestamps', () => {
        for (const c of ['story', 'large', 'missing', 'stale', 'contradictory', 'unknown', 'hostile'])
            for (const r of journalFixture(c))
                expect(journalEntry.safeParse(r).success).toBe(true);
        expect(journalEntry.safeParse({ ...story[4], prompt_text: 'private material' }).success).toBe(false);
        expect(journalEntry.safeParse({ ...story[4], published_at: '2026-10-02T12:00:00+02:00' }).success).toBe(false);
        expect(journalEntry.safeParse({ ...story[4], producer: { id: 'a', role: null, prompt: 'secret' } }).success).toBe(false);
        expect(journalEntry.safeParse({ ...story[4], component: undefined }).success).toBe(false);
    });
    it('orders solely by publication, resolves ties by ID and puts undated last', () => {
        const records = [story[6], story[5], story[4]].sort(comparePublished);
        expect(records.map((r) => r.id)).toEqual(['J-05', 'J-06', 'J-07']);
        expect([...records].reverse().sort(comparePublished).map((r) => r.id)).toEqual(['J-05', 'J-06', 'J-07']);
    });
    it('server pages 10000 entries by 50 and binds cursors to filters', () => {
        const server = new JournalProjector();
        const result = journalSchemas.JournalListResponse.parse(server.read(new URL('http://localhost/api/preview/journal/v0.1/entries?case=large&limit=50')).body);
        expect(result.data.items).toHaveLength(50);
        const token = result.data.next_cursor!;
        expect(server.read(new URL(`http://localhost/api/preview/journal/v0.1/entries?case=large&limit=50&cursor=${token}&kind=discovery`)).status).toBe(400);
        const missing = journalSchemas.JournalListResponse.parse(server.read(new URL('http://localhost/api/preview/journal/v0.1/entries?case=story&limit=50&component_missing=1')).body);
        expect(missing.data.items.map((r) => r.id)).toEqual(['J-07']);
    });
    it('keeps explicit evidence-role fields and precise relation sources', () => {
        const entry = structuredClone(story[4]);
        entry.relations = [{ relation: 'contradicted_by', target: { id: 'NOT-OPPOSING', kind: 'reference', title: null } }];
        const inspection = inspectJournal(entry, { value: journalEnvelope(entry), last_checked_at: 'now' });
        expect(inspection.relations.some((r) => r.field === 'opposing_evidence.0' && r.target.id === 'CLANGD-E880')).toBe(true);
        expect(entry.opposing_evidence.some((r) => r.id === 'NOT-OPPOSING')).toBe(false);
        expect(inspection.relations[0].field).toBe('relations.0.contradicted_by');
    });
    it('Playground distinguishes accepted/provisional and unknown values', () => {
        const future = journalFixture('unknown')[4];
        expect(validateInput('JournalResponse', JSON.stringify(journalEnvelope(future)), journalContract).status).toBe('Accepted shape; unknown semantic values');
        expect(validateInput('JournalResponse', JSON.stringify(journalEnvelope(future))).status).toBe('Unknown registered response schema');
    });
});
describe('Journal transport isolation', () => {
    function reader(request: typeof fetch) {
        const r = new ReadTransport(request, undefined, new RequestLog(), { base: '/api/preview/journal/v0.1', routes: /^\/entries(?:\/|\?|$)/ });
        r.reset({ ...r.context.identity, mode: 'demo', contract: 'journal:0.1.0', dataset: 'story' });
        r.context.bind('aew-demo');
        return r;
    }
    it('preserves 304 provenance, retires late reads and rejects accepted routes', async () => {
        const requests: RequestInit[] = [];
        const r = reader(vi.fn(async (_input, init) => { requests.push(init!); return requests.length === 1 ? new Response(JSON.stringify(journalEnvelope(story[4])), { headers: { 'Content-Type': 'application/json', ETag: '"journal"' } }) : new Response(null, { status: 304 }); }));
        const first = await r.get('/entries/J-05', journalSchemas.JournalResponse);
        const second = await r.get('/entries/J-05', journalSchemas.JournalResponse);
        expect(second.value).toBe(first.value);
        expect(new Headers(requests[1].headers).get('If-None-Match')).toBe('"journal"');
        await expect(r.get('/knowledge/J-05', journalSchemas.JournalResponse)).rejects.toThrow('Invalid API route');
        let finish!: (response: Response) => void;
        const delayed = reader(vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
        const pending = delayed.get('/entries/J-05', journalSchemas.JournalResponse);
        delayed.reset({ ...delayed.context.identity, dataset: 'new-case' });
        finish(new Response(JSON.stringify(journalEnvelope(story[4])), { headers: { 'Content-Type': 'application/json' } }));
        await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    });
    it('access refusal evicts its validator and accepted caches remain independent', async () => {
        const headers: Headers[] = [];
        let ordinal = 0;
        const r = reader(vi.fn(async (_input, init) => { headers.push(new Headers(init?.headers)); ordinal++; return ordinal === 2 ? new Response(null, { status: 403 }) : new Response(JSON.stringify(journalEnvelope(story[4])), { headers: { 'Content-Type': 'application/json', ETag: '"journal"' } }); }));
        await r.get('/entries/J-05', journalSchemas.JournalResponse);
        await expect(r.get('/entries/J-05', journalSchemas.JournalResponse)).rejects.toThrow('Access unavailable');
        await r.get('/entries/J-05', journalSchemas.JournalResponse);
        expect(headers[2].has('If-None-Match')).toBe(false);
        expect(r.context.key('/entries')).not.toBe(transport.context.key('/knowledge'));
    });
});
function mount(route: string) {
    const accepted = new DemoProjector(structuredClone(f1) as World), preview = new JournalProjector();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
        const url = new URL(String(input), 'http://localhost');
        const result = url.pathname.startsWith('/api/preview/') ? preview.read(url) : accepted.read(url);
        return new Response(JSON.stringify(result.body), { status: result.status, headers: { 'Content-Type': 'application/json' } });
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><DashboardProvider><Journal Records={() => <p>Accepted records</p>}/></DashboardProvider></MemoryRouter></QueryClientProvider>);
    return client;
}
describe('Journal investigation UI', () => {
    it('has explicit missing explanation and evidence and preserves selection under filters', async () => {
        mount('/knowledge?selected=J-05&journal_case=missing');
        await screen.findByText('No retention explanation supplied.');
        fireEvent.click(screen.getByRole('tab', { name: 'Evidence' }));
        expect(screen.getByText('No supporting evidence references supplied.')).toBeTruthy();
        expect(screen.getByText('No opposing evidence references supplied.')).toBeTruthy();
        fireEvent.change(screen.getByLabelText('Component'), { target: { value: 'missing' } });
        await screen.findByText('Selected entry is outside these results. Its detail remains selected.');
        expect(screen.getByRole('tab', { name: 'Evidence' }).getAttribute('aria-selected')).toBe('true');
    });
    it('exposes the full fictional chain without developer tools', async () => {
        mount('/knowledge?selected=J-05');
        await screen.findByText('Conditional lesson: refresh the compilation database before using missing clangd references as evidence that a function is unused.');
        fireEvent.click(screen.getByRole('tab', { name: 'Evidence' }));
        expect(screen.getByText(/CLANGD-E880/)).toBeTruthy();
        fireEvent.click(screen.getByRole('tab', { name: 'Provenance' }));
        expect(screen.getByText(/CLANGD-D42/)).toBeTruthy();
        expect(screen.getByText('The graph contains only loaded supplied relations within the displayed bounds. Absence of a relationship is not evidence that no relationship exists.')).toBeTruthy();
        fireEvent.click(screen.getByRole('link', { name: /J-03 · derived_from/ }));
        await screen.findByText(/Failed removal: deleting the function/);
    });
    it('guards unsupported historical scope without journal requests', async () => {
        mount('/knowledge?rev=41&selected=J-05');
        await screen.findByText('Historical snapshot reads are not supported by this preview.');
        await waitFor(() => expect(transport.context.projectId).toBe('aew-demo'));
        const spy = vi.mocked(globalThis.fetch);
        expect(spy.mock.calls.some(([url]) => String(url).includes('/api/preview/'))).toBe(false);
    });
});
