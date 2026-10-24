import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../src/stg02/App';
import { validated } from '../src/stg02/wire';
import run from './fixtures/stg02/run.json';
import owner from './fixtures/stg02/owner-operation-get.json';
import empty from './fixtures/stg02/index-empty.json';
import request from '../src/stg02/contracts/fixture-continue-request.json';
import { persistRecovery } from '../src/stg02/recovery';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); window.history.replaceState({}, '', '/'); });
function serve(view: string, id: string, body: unknown, headers: HeadersInit) {
  window.history.replaceState({}, '', `/stg02?${new URLSearchParams({ view, id })}`);
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { headers })));
  render(<App />);
}
describe('STG-02 read-state and identity regressions', () => {
  it.each(['unavailable', 'unsupported'] as const)('renders a valid empty %s run without inventing an item', async outcome => {
    const body = { ...run, outcome, continuity: 'unknown', items: [], limitations: outcome === 'unavailable' ? ['source_unavailable'] : [] };
    // Schema itself defines the legal empty outcomes, independently of the view.
    expect(validated('run', body)).toEqual(body);
    serve('run', 'invocation:demo-1', body, { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-Wire-Version': '0.3.4' });
    await screen.findByRole('heading', { name: `Read outcome: ${outcome}` });
    expect(screen.queryByRole('alert')).toBeNull();
  });
  it('still rejects a present run with the wrong identity', async () => {
    serve('run', 'invocation:other', run, { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-Wire-Version': '0.3.4' });
    expect((await screen.findByRole('alert')).textContent).toContain('binding');
    expect(screen.queryByRole('heading', { name: 'Remote effect' })).toBeNull();
  });
  it.each(['owner', 'operation_ref', 'intent_ref', 'combined'])('rejects contradictory nested operation %s before showing an outcome', async field => {
    const body = structuredClone(owner.ATTACH_LEAD.body);
    const values = { owner: 'ADC', operation_ref: 'op:other', intent_ref: 'intent:other' };
    for (const key of Object.keys(values) as (keyof typeof values)[]) if (field === key || field === 'combined') body.result[key] = values[key];
    body.result.effect_state = 'EFFECT_CONFIRMED';
    serve('operation', 'HEB|op:attach-lead', body, owner.ATTACH_LEAD.headers);
    expect((await screen.findByRole('alert')).textContent).toContain('binding');
    expect(screen.queryByRole('heading', { name: 'Read outcome: EFFECT_CONFIRMED' })).toBeNull();
  });
  it('accepts the internally consistent owner specimen without claiming world qualification', async () => {
    serve('operation', 'HEB|op:attach-lead', owner.ATTACH_LEAD.body, owner.ATTACH_LEAD.headers);
    await screen.findByRole('heading', { name: 'Read outcome: UNKNOWN_EFFECT' });
    expect(screen.queryByRole('alert')).toBeNull();
  });
  it.each(['request_set_ref', 'recipient_ref', 'installation_ref', 'intent_ref'] as const)('checks known originating %s after receipt and reload', async field => {
    const body = { ...structuredClone(owner.ATTACH_LEAD.body), request_set_ref: request.request_set_ref,
      recipient_ref: request.recipient_ref, installation_ref: request.installation_ref, intent_ref: request.intents[0].intent_ref };
    body.result.intent_ref = request.intents[0].intent_ref;
    persistRecovery({ version: 1, body: JSON.stringify(request), phase: 'lookup', receipt: {
      wire_version: body.wire_version, request_set_ref: request.request_set_ref, recipient_ref: request.recipient_ref,
      carrier_state: 'RECEIVED', observed_at: body.observed_at, source_valid_until: body.source_valid_until, results: [body.result],
    } });
    body[field] = 'identity:other';
    if (field === 'intent_ref') body.result.intent_ref = body.intent_ref;
    serve('operation', 'HEB|op:attach-lead', body, owner.ATTACH_LEAD.headers);
    expect((await screen.findByRole('alert')).textContent).toContain('original request/owner-operation binding');
  });
  it('shows collection provenance even when the qualified scoped list has no items', async () => {
    serve('operations', '', empty.body, empty.headers);
    await screen.findByRole('heading', { name: 'Read outcome: provided' });
    const section = screen.getByRole('heading', { name: 'Collection basis — aggregation only' }).parentElement!;
    expect(section.textContent).toContain('basis:roster');
    expect(section.textContent).toContain('CNI');
    expect(section.textContent).toContain('qualified');
    expect(section.textContent).toContain('2026-10-19T13:00:00Z');
    expect(screen.getByText('None in the requested recipient scope. This is not global absence.')).toBeDefined();
  });
});
