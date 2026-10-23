import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ContinueControl } from '../src/stg02/App';
import request from '../src/stg02/contracts/fixture-continue-request.json';
import problems from './fixtures/stg02/problems.json';
import { O01_VERSION, validated } from '../src/stg02/wire';

beforeEach(() => { sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); sessionStorage.clear(); });
function select() {
  fireEvent.click(screen.getByRole('button', { name: 'Review work supplied by the fixture delegation' }));
  fireEvent.click(screen.getByRole('checkbox'));
}
function receipt() {
  return new Response(JSON.stringify({ wire_version: O01_VERSION, request_set_ref: request.request_set_ref,
    recipient_ref: request.recipient_ref, carrier_state: 'RECEIVED', observed_at: '2026-10-18T13:00:00Z', source_valid_until: '2026-10-19T13:00:00Z', results: request.intents.map(intent => ({
      intent_ref: intent.intent_ref, owner: intent.owner_hint, admission_state: 'RECEIVED', effect_state: 'NOT_OBSERVED', cancellation_state: 'NONE', operation_ref: null, owner_evidence_ref: null, reason_code: null, residual_remote_effect: 'NOT_ESTABLISHED',
    })) }), { status: 202, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-O01-Wire': O01_VERSION } });
}

describe('STG-02 independent operator command flow', () => {
  it('requires deliberate selection, persists before send, prevents duplicate pending sends, and reconciles identical body/key after loss', async () => {
    let reject!: (failure: Error) => void;
    const bodies: string[] = [];
    const fetcher = vi.fn((_path: RequestInfo | URL, init?: RequestInit) => {
      const body = String(init?.body); bodies.push(body);
      expect(JSON.parse(sessionStorage.getItem(sessionStorage.key(0)!)!).body).toBe(body);
      return bodies.length === 1 ? new Promise<Response>((_resolve, fail) => { reject = fail; }) : Promise.resolve(receipt());
    });
    vi.stubGlobal('fetch', fetcher);
    render(<ContinueControl />);
    fireEvent.click(screen.getByRole('button', { name: 'Review work supplied by the fixture delegation' }));
    const submit = screen.getByRole('button', { name: 'Submit selected work to HEB' });
    expect(submit.hasAttribute('disabled')).toBe(true); expect(fetcher).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(submit); fireEvent.click(submit);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => reject(new Error('Lost response')));
    expect(screen.getByRole('alert').textContent).toContain('owner outcome is not established');
    fireEvent.click(screen.getByRole('button', { name: 'Reconcile using the same key and exact body' }));
    await screen.findByRole('heading', { name: '202 — received, not done' });
    expect(bodies).toHaveLength(2); expect(bodies[1]).toBe(bodies[0]);
    expect(JSON.parse(bodies[0]).client_request_key).toBe(request.client_request_key);
  });
  it('does not retry a 409 key conflict', async () => {
    const conflict = problems.find(item => item.body.code === 'request_key_conflict')!;
    expect(conflict).toBeDefined();
    const fetcher = vi.fn(async () => new Response(JSON.stringify(conflict.body), { status: 409, headers: {
      'Content-Type': 'application/problem+json', 'Cache-Control': 'private, no-store', 'X-AEW-O01-Wire': O01_VERSION,
    } }));
    vi.stubGlobal('fetch', fetcher);
    render(<ContinueControl />); select();
    fireEvent.click(screen.getByRole('button', { name: 'Submit selected work to HEB' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: 'Reconcile using the same key and exact body' }).hasAttribute('disabled')).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it.each([
    ['invalid_request', 400], ['not_found_or_not_disclosable', 404],
    ['request_key_conflict', 409], ['unsupported_action', 400], ['unresolved_no_redispatch', 409],
  ] as const)('preserves terminal %s across reload and forbids another POST', async (code, status) => {
    const body = { code, status, retry: 'never', type: 'about:blank', title: 'Request could not be completed', correlation_id: 'correlation:one' };
    expect(validated('o01Problem', body)).toEqual(body);
    const fetcher = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: {
      'Content-Type': 'application/problem+json', 'Cache-Control': 'private, no-store', 'X-AEW-O01-Wire': O01_VERSION,
    } }));
    vi.stubGlobal('fetch', fetcher);
    const mount = render(<ContinueControl />); select();
    fireEvent.click(screen.getByRole('button', { name: 'Submit selected work to HEB' }));
    await screen.findByRole('alert');
    const reconcile = () => screen.getByRole('button', { name: 'Reconcile using the same key and exact body' });
    expect(reconcile().hasAttribute('disabled')).toBe(true);
    fireEvent.click(reconcile());
    mount.unmount(); render(<ContinueControl />);
    await screen.findByText(/Retry guidance: never/);
    expect(reconcile().hasAttribute('disabled')).toBe(true);
    fireEvent.click(reconcile());
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'Inspect owner-operation outcomes' })).toBeDefined();
  });
  it.each([
    ['authentication_unqualified', 401, 'reauthenticate'], ['precondition_changed', 409, 'refresh_read'],
    ['owner_unavailable', 503, 'when_source_recovers'], ['operator_origin_not_established', 401, 'not_established'],
  ] as const)('shows and preserves the %s prerequisite without asserting it has been satisfied', async (code, status, retry) => {
    const body = { code, status, retry, type: 'about:blank', title: 'Request could not be completed', correlation_id: 'correlation:one' };
    expect(validated('o01Problem', body)).toEqual(body);
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status, headers: {
      'Content-Type': 'application/problem+json', 'Cache-Control': 'private, no-store', 'X-AEW-O01-Wire': O01_VERSION,
    } })));
    const mount = render(<ContinueControl />); select();
    fireEvent.click(screen.getByRole('button', { name: 'Submit selected work to HEB' }));
    await screen.findByRole('alert'); mount.unmount(); render(<ContinueControl />);
    await screen.findByText(new RegExp(`Retry guidance: ${retry}`));
    expect(screen.getByRole('button', { name: 'Reconcile using the same key and exact body' }).hasAttribute('disabled')).toBe(true);
  });
  it('reload exposes recovery and owner reads without dispatching another command', async () => {
    const fetcher = vi.fn(async () => receipt());
    vi.stubGlobal('fetch', fetcher);
    const mount = render(<ContinueControl />); select();
    fireEvent.click(screen.getByRole('button', { name: 'Submit selected work to HEB' }));
    await screen.findByRole('heading', { name: '202 — received, not done' });
    mount.unmount(); render(<ContinueControl />);
    await screen.findByRole('button', { name: 'Reconcile using the same key and exact body' });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'Inspect owner-operation outcomes' }).getAttribute('href')).toBe('/stg02?view=operations');
  });
  it('refuses dispatch when exact-request recovery cannot be persisted', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable'); });
    render(<ContinueControl />); select();
    fireEvent.click(screen.getByRole('button', { name: 'Submit selected work to HEB' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Storage unavailable'));
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('fails closed after reload when persisting a terminal response fails', async () => {
    const original = Storage.prototype.setItem;
    let writes = 0;
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
      if (++writes > 1) throw new Error('Storage update unavailable');
      original.call(this, key, value);
    });
    const body = { code: 'unresolved_no_redispatch', status: 409, retry: 'never', type: 'about:blank', title: 'Request could not be completed', correlation_id: 'correlation:one' };
    const fetcher = vi.fn(async () => new Response(JSON.stringify(body), { status: 409, headers: {
      'Content-Type': 'application/problem+json', 'Cache-Control': 'private, no-store', 'X-AEW-O01-Wire': O01_VERSION,
    } }));
    vi.stubGlobal('fetch', fetcher);
    const mount = render(<ContinueControl />); select();
    fireEvent.click(screen.getByRole('button', { name: 'Submit selected work to HEB' }));
    await screen.findByRole('alert');
    expect(screen.getByText(/Retry guidance: never/)).toBeDefined();
    mount.unmount(); render(<ContinueControl />);
    const lookup = await screen.findByRole('button', { name: 'Reconcile using the same key and exact body' });
    expect(lookup.hasAttribute('disabled')).toBe(true);
    fireEvent.click(lookup); expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
