import { validators } from './validators.generated.js';
export { compatibleSchema } from './schema-compat';

export const D01_VERSION = '0.3.4';
export const O01_VERSION = 'o01-command-0.2-review-candidate';
export const PACKAGE_DIGEST = '64e65578e9774fd9425c19ceaff30f1a0018ae819baa58d9469ed0c33e8f299f';
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type ObjectValue = { [key: string]: Json };
export const object = (value: Json | undefined): ObjectValue =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value : {};
export const array = (value: Json | undefined): Json[] => Array.isArray(value) ? value : [];
export const text = (value: Json | undefined) => value === null || value === undefined ? 'Not supplied' : typeof value === 'object' ? JSON.stringify(value) : String(value);

export type ReadKind = 'waiting' | 'run' | 'continuation' | 'operations' | 'operation';
export function validated(kind: keyof typeof validators, value: unknown): ObjectValue {
  const validate = validators[kind];
  if (!validate(value)) throw new Error(`Rejected ${kind} structure: ${validate.errors?.map(error => `${error.dataPath ?? ''} ${error.message ?? ''}`).join('; ')}`);
  const body = value as ObjectValue;
  if (kind === 'operation' && ['owner', 'operation_ref', 'intent_ref'].some(key => body[key] !== object(body.result)[key]))
    throw new Error('Rejected owner-operation result binding');
  return body;
}

export class WireProblem extends Error {
  constructor(public status: number, public body: ObjectValue) {
    super(status === 404 ? 'Not found or not disclosable' : `${status}: ${text(body.code)}`);
  }
}

export function readPath(kind: ReadKind, id = '', cursor = ''): string {
  if (kind === 'run' || kind === 'continuation') {
    if (!id || id.length > 225) throw new Error('Invalid exact resource identity');
    const bytes = new TextEncoder().encode(id);
    if (new TextDecoder('utf-8', { fatal: true }).decode(bytes) !== id) throw new Error('Invalid UTF-8 resource identity');
    const encoded = window.btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
    if (encoded.length > (kind === 'run' ? 300 : 256)) throw new Error('Resource identity exceeds selected path bound');
    return `/v1/read/${kind === 'run' ? 'runs' : 'continuation-state'}/${encoded}`;
  }
  if (kind === 'operation') {
    const [owner, operation, extra] = id.split('|');
    if (extra !== undefined || !/^[A-Za-z][A-Za-z0-9:._/-]{2,127}$/.test(owner ?? '') || !/^[A-Za-z][A-Za-z0-9:._-]{2,127}$/.test(operation ?? ''))
      throw new Error('Invalid owner/operation identity');
    return `/o01/v0/owner-operations/${encodeURIComponent(owner)}/${encodeURIComponent(operation)}`;
  }
  const query = new URLSearchParams(kind === 'waiting' ? { limit: '25' } : undefined);
  if (cursor) query.set('cursor', cursor);
  return `/v1/read/${kind === 'waiting' ? 'waiting' : 'owner-operations'}${query.size ? '?' + query : ''}`;
}

export type Transport = typeof fetch;
export async function exchange(kind: ReadKind | 'receipt', path: string, signal: AbortSignal,
  transport: Transport = fetch, body?: string): Promise<ObjectValue> {
  const o01 = kind === 'operation' || kind === 'receipt';
  const response = await transport(path, {
    method: body === undefined ? 'GET' : 'POST', cache: 'no-store', credentials: 'same-origin', redirect: 'error', signal,
    headers: { [o01 ? 'X-AEW-O01-Wire' : 'X-AEW-Wire-Version']: o01 ? O01_VERSION : D01_VERSION,
      Accept: 'application/json, application/problem+json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body }),
  });
  if (response.headers.get(o01 ? 'X-AEW-O01-Wire' : 'X-AEW-Wire-Version') !== (o01 ? O01_VERSION : D01_VERSION) ||
      response.headers.get('Cache-Control') !== 'private, no-store') throw new Error('Rejected version or no-store response headers');
  const expectedType = response.ok ? 'application/json' : 'application/problem+json';
  if (response.headers.get('Content-Type')?.split(';')[0].trim() !== expectedType) throw new Error('Rejected response media type');
  const raw: unknown = await response.json();
  if (!response.ok) {
    const problem = validated(o01 ? 'o01Problem' : 'd01Problem', raw);
    if (problem.status !== response.status) throw new Error('Rejected Problem status mismatch');
    throw new WireProblem(response.status, problem);
  }
  if (response.status !== (kind === 'receipt' ? 202 : 200)) throw new Error('Unexpected success status');
  const result = validated(kind, raw);
  if (signal.aborted) throw new DOMException('Retired read', 'AbortError');
  return result;
}

// No continuation vector is accepted here. The operator supplies a separate
// request under an independently supplied delegation; only HEB admits it.
export function prepareContinue(value: unknown): string {
  const body = validated('command', value);
  if (array(body.intents).some(intent => object(intent).action !== 'CONTINUE_ELIGIBLE_WORK'))
    throw new Error('Protected or unsupported command: held; G3_unqualified');
  return JSON.stringify(body);
}

export function validateReceiptBinding(receipt: ObjectValue, submitted: string): ObjectValue {
  const request = validated('command', JSON.parse(submitted));
  const intents = array(request.intents), results = array(receipt.results);
  if (receipt.request_set_ref !== request.request_set_ref || receipt.recipient_ref !== request.recipient_ref || results.length !== intents.length ||
      results.some((result, i) => object(result).intent_ref !== object(intents[i]).intent_ref || object(result).owner !== object(intents[i]).owner_hint))
    throw new Error('Rejected receipt/request binding');
  return receipt;
}
