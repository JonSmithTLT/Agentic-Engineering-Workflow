import { array, object, PACKAGE_DIGEST, prepareContinue, validated, validateReceiptBinding } from './wire';
import type { ObjectValue } from './wire';

export const recoveryKey = `aew-stg02-recovery:${PACKAGE_DIGEST}`;
export interface Recovery {
  version: 1;
  body: string;
  phase: 'in_flight' | 'lookup' | 'problem';
  problem?: ObjectValue;
  receipt?: ObjectValue;
}
export function parseRecovery(raw: string): Recovery {
  const value = JSON.parse(raw) as Recovery;
  if (!value || value.version !== 1 || typeof value.body !== 'string' ||
      !['in_flight', 'lookup', 'problem'].includes(value.phase)) throw new Error('Invalid recovery record');
  // Validate the request without replacing its exact serialized bytes.
  prepareContinue(JSON.parse(value.body));
  if (value.phase === 'problem') validated('o01Problem', value.problem);
  else if (value.problem !== undefined) throw new Error('Contradictory recovery state');
  if (value.receipt !== undefined) validateReceiptBinding(validated('receipt', value.receipt), value.body);
  return value;
}
export function loadRecovery(): Recovery | undefined {
  const raw = sessionStorage.getItem(recoveryKey);
  return raw === null ? undefined : parseRecovery(raw);
}
export function persistRecovery(value: Recovery) {
  const serialized = JSON.stringify(value);
  parseRecovery(serialized);
  sessionStorage.setItem(recoveryKey, serialized);
}
export function validateKnownOperation(value: ObjectValue): ObjectValue {
  // Only a received mapping establishes which intent originally named this pair.
  // An unrelated operation does not acquire a fabricated request association.
  const recovery = loadRecovery();
  if (!recovery?.receipt) return value;
  const matched = array(recovery.receipt.results).map(object).find(result =>
    result.owner === value.owner && result.operation_ref === value.operation_ref);
  if (!matched) return value;
  const request = object(JSON.parse(recovery.body));
  if (value.request_set_ref !== request.request_set_ref || value.recipient_ref !== request.recipient_ref ||
      value.installation_ref !== request.installation_ref || value.intent_ref !== matched.intent_ref)
    throw new Error('Rejected original request/owner-operation binding');
  return value;
}
