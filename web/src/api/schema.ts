import { z } from 'zod';

export const id = z.string().min(1);
export const timestamp = z.iso.datetime({ offset: false });
export const reason = z.strictObject({
  code: z.string(),
  message: z.string().nullable(),
});
export const entityRef = z.strictObject({
  id,
  kind: z.string(),
  title: z.string().nullable(),
});
export const richText = z.strictObject({
  format: z.string(),
  text: z.string(),
});
export const capability = z.strictObject({
  state: z.string(),
  reasons: z.array(reason).max(250),
});
export const capabilityNames = [
  'overview',
  'work',
  'runs',
  'evidence',
  'knowledge',
  'history',
  'integrity',
  'queue',
  'action_projection',
  'activity',
] as const;
export const capabilities = z.strictObject(
  Object.fromEntries(
    capabilityNames.map((name) => [name, capability.optional()]),
  ),
);
export const project = z.strictObject({
  id,
  name: z.string(),
  aew_version: z.string(),
});
export const health = z.strictObject({
  status: z.string(),
  reasons: z.array(reason).max(250),
  observed_at: timestamp,
});
export const work = z.strictObject({
  id,
  kind: z.string(),
  title: z.string(),
  state: z.string(),
  parent_id: id.nullable(),
  revision: z.number().int().min(0).nullable(),
  classification: z.string().nullable(),
  assurance: z.string().nullable(),
  has_attention: z.boolean(),
  summary: richText,
  reasons: z.array(reason).max(250),
  related: z.array(entityRef).max(250),
  updated_at: timestamp,
});
export const run = z.strictObject({
  id,
  work: entityRef,
  status: z.string(),
  role: z.string(),
  started_at: timestamp,
  finished_at: timestamp.nullable(),
  summary: richText,
  evidence: z.array(entityRef).max(250),
  reasons: z.array(reason).max(250),
});
export const evidence = z.strictObject({
  id,
  kind: z.string(),
  result: z.string(),
  subject: entityRef,
  currentness: z.string(),
  requires_disposition: z.boolean(),
  claim: richText,
  body: richText,
  findings: z.array(reason).max(250),
  deviations: z.array(reason).max(250),
  bindings: z.record(z.string(), z.unknown()),
  provenance: z.array(entityRef).max(250),
});
export const knowledge = z.strictObject({
  id,
  kind: z.string(),
  title: z.string(),
  state: z.string(),
  body: richText,
  reasons: z.array(reason).max(250),
  provenance: z.array(entityRef).max(250),
});
export const history = z.strictObject({
  id,
  subject: entityRef,
  recorded_at: timestamp,
  currentness: z.string(),
  annotation: z.string(),
  body: richText,
  lineage: z.array(entityRef).max(250),
});
export const integrity = z.strictObject({
  status: z.string(),
  current_root: z.string().nullable(),
  verified_root: z.string().nullable(),
  verified_at: timestamp.nullable(),
  last_full_audit_at: timestamp.nullable(),
  backlog: z.number().int().min(0),
  reasons: z.array(reason).max(250),
});
export const queue = z.strictObject({
  id,
  work: entityRef,
  state: z.string(),
  position: z.number().int().min(0).nullable(),
  commit_ready_seq: z.number().int().min(0).nullable(),
  attempt: z.number().int().min(0).nullable(),
  publication_mode: z.string().nullable(),
  custodian: z.string().nullable(),
  lease_started_at: timestamp.nullable(),
  current_base: z.string().nullable(),
  latest_validation: reason.nullable(),
  reasons: z.array(reason).max(250),
});
export const attention = z.strictObject({
  id,
  kind: z.string(),
  severity: z.string(),
  subject: entityRef,
  title: z.string(),
  summary: richText,
  reasons: z.array(reason).max(250),
  first_seen_at: timestamp,
});
export const activity = z.strictObject({
  id,
  subject: entityRef,
  occurred_at: timestamp,
  title: z.string(),
  reason: reason.nullable(),
});
export const overview = z.strictObject({
  project,
  health,
  summary: richText,
  work: z.array(work).max(6),
  runs: z.array(run).max(6),
  attention: z.array(attention).max(6),
  activity: z.array(activity).max(10),
  counts: z.strictObject({
    work: z.number().int().min(0),
    runs: z.number().int().min(0),
    attention: z.number().int().min(0),
  }),
  capabilities,
});
export const envelope = <T extends z.ZodType>(data: T) =>
  z.strictObject({
    schema_version: z.literal('0.1.0'),
    project_id: id,
    control_revision: id,
    generated_at: timestamp,
    data,
  });
export const collection = <T extends z.ZodType>(item: T) =>
  z.strictObject({ items: z.array(item).max(250), next_cursor: id.nullable() });
export const responseSchemas = {
  ProjectResponse: envelope(project),
  CapabilitiesResponse: envelope(capabilities),
  OverviewResponse: envelope(overview),
  IntegrityResponse: envelope(integrity),
  WorkResponse: envelope(work),
  RunResponse: envelope(run),
  EvidenceResponse: envelope(evidence),
  KnowledgeResponse: envelope(knowledge),
  HistoryResponse: envelope(history),
  WorkListResponse: envelope(collection(work)),
  RunListResponse: envelope(collection(run)),
  EvidenceListResponse: envelope(collection(evidence)),
  KnowledgeListResponse: envelope(collection(knowledge)),
  HistoryListResponse: envelope(collection(history)),
  QueueListResponse: envelope(collection(queue)),
  AttentionListResponse: envelope(collection(attention)),
  ActivityListResponse: envelope(collection(activity)),
};
