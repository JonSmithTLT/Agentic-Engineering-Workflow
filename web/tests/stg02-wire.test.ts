import { describe, expect, it, vi } from 'vitest';
import { compatibleSchema, D01_VERSION, exchange, prepareContinue, readPath, validated, validateReceiptBinding, WireProblem } from '../src/stg02/wire';
import waiting from './fixtures/stg02/waiting.json';
import run from './fixtures/stg02/run.json';
import full from './fixtures/stg02/continuation-full.json';
import partial from './fixtures/stg02/continuation-partial.json';
import first from './fixtures/stg02/index-first.json';
import last from './fixtures/stg02/index-last.json';
import request from './fixtures/stg02/request.json';
import receipt from './fixtures/stg02/receipt.json';
import problems from './fixtures/stg02/problems.json';
import protectedRequest from './fixtures/stg02/protected-request.json';

describe('STG-02 adopted wire boundary', () => {
  it('validates independently recorded D-01 shapes without promoting source qualification', () => {
    for (const [kind, body] of [['waiting', waiting], ['run', run], ['continuation', full.body], ['continuation', partial.body], ['operations', first.body], ['operations', last.body]] as const)
      expect(validated(kind, body)).toEqual(body);
    expect(partial.body.items[0].data.axes.AEV.state).toBe('unknown');
    expect(validated('run', run).items).toEqual(run.items);
  });
  it('rejects unknown fields, wrong wire and false information-only flags', () => {
    expect(() => validated('waiting', { ...waiting, wire_version: '0.3.3' })).toThrow();
    expect(() => validated('waiting', { ...waiting, clearance: true })).toThrow();
    const invalid = structuredClone(full.body);
    invalid.items[0].data.informational_only = false;
    expect(() => validated('continuation', invalid)).toThrow();
    expect(() => compatibleSchema({ contains: {}, minContains: 2 })).toThrow();
    expect(() => compatibleSchema({ unevaluatedProperties: false })).toThrow();
    // Draft 2020-12 validates assertions beside $ref. Ajv 6 ignores them by
    // default; this discriminates that unsafe compatibility configuration.
    const badClosure = structuredClone(last.body);
    badClosure.collection_basis.qualification = 'unqualified';
    badClosure.collection_basis.observation_state = 'unknown';
    expect(() => validated('operations', badClosure)).toThrow();
  });
  it('requires the exact wire headers and no-store, and never adds dashboard queries', async () => {
    const transport = vi.fn(async () => new Response(JSON.stringify(waiting), { headers: {
      'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-Wire-Version': D01_VERSION,
    } }));
    const signal = new AbortController().signal;
    const path = readPath('waiting', '', 'opaque:cursor');
    await expect(exchange('waiting', path, signal, transport)).resolves.toEqual(waiting);
    expect(path).toBe('/v1/read/waiting?limit=25&cursor=opaque%3Acursor');
    expect(transport.mock.calls[0]).toHaveLength(2);
    const missingHeader = vi.fn(async () => new Response(JSON.stringify(waiting), { headers: { 'Content-Type': 'application/json' } }));
    await expect(exchange('waiting', path, signal, missingHeader)).rejects.toThrow('headers');
  });
  it('keeps nondisclosure as one 404 state, never an empty green list', async () => {
    const problem = problems.find(x => x.status === 404)!;
    const headers = Object.fromEntries(Object.entries(problem.headers).filter((entry): entry is [string, string] => typeof entry[1] === 'string'));
    const transport = vi.fn(async () => new Response(JSON.stringify(problem.body), { status: 404, headers }));
    await expect(exchange('waiting', readPath('waiting'), new AbortController().signal, transport)).rejects.toBeInstanceOf(WireProblem);
    await expect(exchange('waiting', readPath('waiting'), new AbortController().signal, transport)).rejects.toThrow('Not found or not disclosable');
  });
  it('only prepares separate C17 requests and binds receipt results in request order', () => {
    const serialized = prepareContinue(request);
    expect(JSON.parse(serialized)).toEqual(request);
    expect(validateReceiptBinding(validated('receipt', receipt), serialized)).toEqual(receipt);
    expect(() => prepareContinue(full.body)).toThrow();
    expect(validated('command', protectedRequest)).toEqual(protectedRequest);
    expect(() => prepareContinue(protectedRequest)).toThrow('Protected or unsupported command: held; G3_unqualified');
    expect(() => validateReceiptBinding({ ...receipt, request_set_ref: 'other:set' }, serialized)).toThrow('binding');
    expect(() => validateReceiptBinding({ ...receipt, results: [] }, serialized)).toThrow('binding');
  });
  it('encodes exact identities and refuses malformed owner-operation and read locators', () => {
    expect(readPath('run', 'invocation:demo-1')).toBe('/v1/read/runs/aW52b2NhdGlvbjpkZW1vLTE');
    expect(readPath('continuation', 'ticket:one')).toBe('/v1/read/continuation-state/dGlja2V0Om9uZQ');
    expect(readPath('operations')).toBe('/v1/read/owner-operations');
    expect(readPath('operation', 'HEB|op:one')).toBe('/o01/v0/owner-operations/HEB/op%3Aone');
    expect(() => readPath('operation', 'HEB|op:one|unexpected')).toThrow();
    expect(() => readPath('run', '\ud800')).toThrow();
  });
  it('does not publish a late successful noncooperative transport after retirement', async () => {
    const controller = new AbortController();
    let resolve!: (response: Response) => void;
    const transport = vi.fn(() => new Promise<Response>(done => { resolve = done; }));
    const pending = exchange('waiting', readPath('waiting'), controller.signal, transport);
    controller.abort();
    resolve(new Response(JSON.stringify(waiting), { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-Wire-Version': D01_VERSION } }));
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});
