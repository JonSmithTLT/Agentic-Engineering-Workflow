// F46.1 proposal v10 Appendix A. Fixture-only; not an adopted API registration.
import { z } from 'zod';
import { capability, controlRevision, id, timestamp } from '../../schema';
const text = z.string().refine(value => new TextEncoder().encode(value).length <= 512, 'Maximum 512 UTF-8 bytes');
const path = text.refine(value => (value === '' || value.startsWith('/')) && new TextEncoder().encode(value).length <= 256, 'Configuration display locator');
const scalar = z.union([text, z.number().finite(), z.boolean(), z.null()]);
const digest = z.string().regex(/^sha256:[0-9a-f]{64}$/);
export const fieldValue = z.strictObject({
  path, state: z.enum(['SET', 'NULL', 'ABSENT']), value: scalar.optional(), withheld: text.optional(),
  effective: scalar.optional(), effective_source: text.optional(), class: text, allowed: z.array(text).max(16).optional(),
  description: text.optional(), edit: text, editable: z.boolean(),
}).superRefine((field, context) => {
  const owns = Object.hasOwn(field, 'value');
  if (field.state === 'SET' ? field.withheld !== undefined ? owns : !owns || field.value === null : field.state === 'NULL' ? !owns || field.value !== null : owns)
    context.addIssue({ code: 'custom', message: 'Invalid configured value presence', path: ['value'] });
  if (field.withheld !== undefined && field.state !== 'SET') context.addIssue({ code: 'custom', message: 'Only SET may be withheld' });
  if (field.editable) context.addIssue({ code: 'custom', message: 'F46.1 fixtures are read-only' });
});
export type FieldValue = z.infer<typeof fieldValue>;
const routeTable = z.strictObject({ entries: z.array(z.strictObject({ key: text.nullable(), index: z.number().int().nonnegative(), profile: fieldValue })).max(256), truncated: z.boolean() });
export const executionProfile = z.strictObject({
  name: text.nullable(), index: z.number().int().nonnegative(),
  fields: z.strictObject({ harness: fieldValue, provider: fieldValue, model: fieldValue, effort: fieldValue, max_steps: fieldValue, deadline_s: fieldValue, description: fieldValue }),
  identity: z.strictObject({ catalog_id: text, provider: text, model: text, harness_ref: text }).nullable(), identity_rule: text,
  identity_error: z.strictObject({ code: text, withheld_reason: text.nullable(), field_path: path, suggestion: text.nullable(), hint: text }).nullable(),
  connection_id: text.nullable(), routed_by: z.array(text).max(64), routed_by_truncated: z.boolean(),
});
export type ExecutionProfile = z.infer<typeof executionProfile>;
const connection = z.strictObject({
  connection_id: z.string().regex(/^conn-[0-9a-f]{16}$/), harness: text, provider: text, profiles: z.array(z.number().int().nonnegative()).max(64), profiles_truncated: z.boolean(),
  credential_sources: z.strictObject({ provider_env: z.strictObject({ scope: z.literal('policy_wide'), ref: z.literal('/provider_env') }), saved_login: z.literal('NOT_SUPPLIED') }),
  endpoint: z.literal('NOT_SUPPLIED'), catalog: capability,
});
export const configurationIndex = z.strictObject({
  manifest: z.strictObject({ state: text }), activities: z.array(z.strictObject({ activity: text, capability })).max(8),
  documents: z.array(z.strictObject({ document: text.nullable(), index: z.number().int().nonnegative(), same_file_as: z.number().int().nonnegative().nullable(), supported: capability, state: text, in_force: z.boolean(), digest, write: capability })).max(16), documents_truncated: z.boolean(),
});
export const executionConfiguration = z.strictObject({
  document: z.strictObject({ state: text, in_force: z.boolean(), digest, on_disk_matches_adopted: z.boolean(), write: capability,
    violations: z.array(z.strictObject({ path, code: text, expected: text.nullable(), extra_key: text.nullable() })).max(50), violations_truncated: z.boolean(),
    yaml_error: z.strictObject({ code: z.literal('YAML_SYNTAX'), line: z.number().int().positive().nullable(), column: z.number().int().positive().nullable() }).nullable(),
  }), configured: fieldValue, harness: fieldValue, description: fieldValue,
  profiles: z.array(executionProfile).max(64), profiles_truncated: z.boolean(),
  routing: z.strictObject({ default: fieldValue, classes: routeTable, archetypes: routeTable, cards: routeTable, resolution_order: z.array(text).max(4) }),
  connections: z.array(connection).max(32), connections_truncated: z.boolean(),
  provider_env: z.strictObject({ state: fieldValue, entries: z.array(z.strictObject({ index: z.number().int().nonnegative(), name: text.nullable(), valid_name: z.boolean() })).max(64), entries_truncated: z.boolean() }),
  observed: z.strictObject({ checked_in: text, caption: text, provider_env: z.array(z.strictObject({ index: z.number().int().nonnegative(), name: text.nullable(), present: z.boolean(), problem: text.nullable() })).max(64), provider_env_truncated: z.boolean() }),
  controls: z.strictObject({
    steering: z.strictObject({ mode: fieldValue, envelope: z.strictObject({ loop_deadline_s: fieldValue, max_auto_actions: fieldValue, repetition_n: fieldValue }), effective: z.strictObject({ mode: text.nullable(), source: text }) }),
    containment: z.strictObject({ mode: fieldValue, writable_count: z.number().int().nonnegative(), hide_count: z.number().int().nonnegative(), trusted_git_drivers_count: z.number().int().nonnegative(), effective: z.literal('NOT_SUPPLIED') }),
    switches: z.array(z.strictObject({ path, value: fieldValue, default: text })).max(16),
    notify: z.strictObject({ configured: z.boolean(), timeout_s: fieldValue, max_output_bytes: fieldValue }),
  }), pins_note: text,
});
const envelope = { schema_version: z.literal('0.1.4'), project_id: id, control_revision: controlRevision, generated_at: timestamp };
export const indexResponse = z.strictObject({ ...envelope, data: configurationIndex });
export const executionResponse = z.strictObject({ ...envelope, data: executionConfiguration });
export type SettingsIndex = z.infer<typeof indexResponse>;
export type SettingsExecution = z.infer<typeof executionResponse>;
export const settingsCases = ['adopted', 'drifted', 'unpin', 'manifest', 'invalid', 'absent', 'withheld', 'partial', 'empty', 'unknown', 'long', 'error', 'loading'] as const;
export type SettingsCase = typeof settingsCases[number];
export interface SettingsSource {
  readIndex(project: string, scenario: SettingsCase, signal: AbortSignal): Promise<unknown>;
  readExecution(project: string, scenario: SettingsCase, signal: AbortSignal): Promise<unknown>;
}
