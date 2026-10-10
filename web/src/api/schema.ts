import { z } from 'zod';
export const id = z
  .string()
  .min(1)
  .regex(/^[A-Za-z0-9][A-Za-z0-9._-]*$/);
export const cursor = z.string().min(1);
export const controlRevision = z.string().regex(/^(0|[1-9][0-9]*)$/);
export const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
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
  'maps',
  'history_search',
  'integrity',
  'queue',
  'action_projection',
  'activity',
] as const;
// New capability names are valid data, never a validation failure or permission.
export const capabilities = z.record(z.string(), capability);
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
export const workCounts = z.strictObject({
  open: z.number().int().min(0),
  done: z.number().int().min(0),
  cancelled: z.number().int().min(0),
});
export const integration = z.strictObject({
  status: z.string().nullable(),
  commit: z.string().nullable(),
  commit_ready_seq: z.number().int().min(0).nullable(),
});
export const work = z.strictObject({
  id,
  kind: z.string(),
  title: z.string(),
  state: z.string(),
  parent_id: id.nullable(),
  risk_class: z.number().int().min(0).max(4).nullable(),
  plan_revision: z.number().int().min(1).nullable(),
  mutating: z.boolean().nullable(),
  archived: z.boolean(),
  blocked_by: z.array(reason).max(250),
  children: z.array(id).max(250),
  children_truncated: z.boolean(),
  rollup: workCounts.nullable(),
  integration: integration.nullable(),
  has_attention: z.boolean(),
  summary: richText,
  reasons: z.array(reason).max(250),
  related: z.array(entityRef).max(250),
  updated_at: timestamp,
});
export const harnessRun = z.strictObject({
  id,
  harness: id,
  launched_at: timestamp,
  kind: z.string(),
  status: z.string(),
  authority: z.string(),
});
export const invocation = z.strictObject({
  id,
  role: z.string(),
  status: z.string(),
  work: entityRef,
  created_at: timestamp,
  runs: z.array(harnessRun).max(250),
  summary: richText,
  evidence: z.array(entityRef).max(250),
  reasons: z.array(reason).max(250),
});
export const evaluatedSnapshot = z.strictObject({
  base_revision: z.string().nullable(),
  relevant_inputs_fingerprint: z.string(),
  artifact_digests: z.array(z.string()).max(250),
});
export const evidencePlanRevision = z.strictObject({
  revision: z.number().int().min(1),
  sha256,
});
export const producer = z.strictObject({
  role: z.string(),
  invocation: id,
  run: id.nullable(),
  model: z.string().nullable(),
  provider: z.string().nullable(),
  harness: id.nullable(),
});
export const evidenceBindings = z.strictObject({
  evaluated_snapshot: evaluatedSnapshot.nullable(),
  plan_revision: evidencePlanRevision.nullable(),
  producer,
});
export const evidence = z.strictObject({
  id,
  kind: z.string(),
  result: z.string().nullable(),
  subject: entityRef,
  currentness: z.string(),
  requires_disposition: z.boolean(),
  claim: richText,
  body: richText,
  findings: z.array(reason).max(250),
  deviations: z.array(reason).max(250),
  bindings: evidenceBindings,
  provenance: z.array(entityRef).max(250),
});
export const knowledge = z.strictObject({
  id,
  kind: z.string(),
  decision_type: z.string().nullable(),
  title: z.string(),
  state: z.string(),
  body: richText,
  reasons: z.array(reason).max(250),
  provenance: z.array(entityRef).max(250),
});
export const annotation = z.strictObject({
  id,
  rel: z.string(),
  object: id.nullable(),
  at: timestamp,
  decision: id.nullable(),
  source: z.string(),
  note: z.string().nullable(),
});
export const history = z.strictObject({
  seq: z.number().int().min(1),
  kind: z.string(),
  id,
  at: timestamp,
  state: z.string().nullable(),
  unit_kind: z.string().nullable(),
  title: z.string().nullable(),
  parent: id.nullable(),
  subject: id.nullable(),
  rel: z.string().nullable(),
  links: z.record(z.string(), z.array(id).max(250)),
  sha256,
  source: z.string(),
});
export const historyDetail = history.extend({
  annotations: z.array(annotation).max(250),
  annotations_next_cursor: cursor.nullable(),
});
export const historyRoot = z.strictObject({
  count: z.number().int().min(0),
  head_h: sha256,
  sealed_head: z
    .strictObject({ seq: z.number().int().min(1), sha256 })
    .nullable(),
});
export const verifiedRoot = z.strictObject({
  count: z.number().int().min(0),
  h: sha256,
  at: timestamp,
  audit: id,
});
export const integrity = z.strictObject({
  status: z.string(),
  current_root: historyRoot,
  verified: verifiedRoot.nullable(),
  last_full: verifiedRoot.nullable(),
  oldest_unverified_at: timestamp.nullable(),
  backlog: z.number().int().min(0),
  last_audit: entityRef.nullable(),
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
  recent: z.array(work).max(20),
  runs: z.array(invocation).max(6),
  attention: z.array(attention).max(6),
  activity: z.array(activity).max(10),
  counts: z.strictObject({
    work: workCounts,
    runs: z.number().int().min(0),
    attention: z.number().int().min(0),
  }),
  capabilities,
});
export const envelope = <T extends z.ZodType, V extends '0.1.2' | '0.1.3' = '0.1.2'>(data: T, version: V = '0.1.2' as V) =>
  z.strictObject({
    schema_version: z.literal(version),
    project_id: id,
    control_revision: controlRevision,
    generated_at: timestamp,
    data,
  });
export const collection = <T extends z.ZodType>(item: T) =>
  z.strictObject({
    items: z.array(item).max(250),
    next_cursor: cursor.nullable(),
  });
export const responseSchemas = {
  ProjectResponse: envelope(project),
  CapabilitiesResponse: envelope(capabilities),
  OverviewResponse: envelope(overview),
  IntegrityResponse: envelope(integrity),
  WorkResponse: envelope(work),
  InvocationResponse: envelope(invocation),
  EvidenceResponse: envelope(evidence),
  KnowledgeResponse: envelope(knowledge),
  HistoryResponse: envelope(historyDetail),
  WorkListResponse: envelope(collection(work)),
  InvocationListResponse: envelope(collection(invocation)),
  EvidenceListResponse: envelope(collection(evidence)),
  KnowledgeListResponse: envelope(collection(knowledge)),
  HistoryListResponse: envelope(collection(history)),
  AttentionListResponse: envelope(collection(attention)),
  ActivityListResponse: envelope(collection(activity)),
};
