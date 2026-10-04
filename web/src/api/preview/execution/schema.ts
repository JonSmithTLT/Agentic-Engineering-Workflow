import { z } from 'zod';
// @ts-expect-error Explicit extension supports the pinned artifact runner.
import { id, timestamp, entityRef, invocation, reason } from '../../schema.ts';
const semantic = z.string().min(1).max(128), text = z.string().max(4096), meta = z.string().max(512).nullable();
const refs = z.array(entityRef).max(80);
export const executionCases = ['story','large','fanout','partial','cycles','unordered','unknown','missing','stale','mismatch','denied','historical-unavailable','malformed','refresh-error','hostile','empty'] as const;
export const lanes = ['invocation','tools','evidence','reviews','transitions','context'];
export const relationKinds = ['registered_child_invocation','process_spawned_process','harness_launched_helper','provider_suboperation','trace_correlation'];
export const binding = z.strictObject({ source_id:id, snapshot_id:id, project_id:id });
export const endpoint = z.strictObject({ id, kind:semantic });
export const relation = z.strictObject({ id, relation_kind:semantic, from:endpoint, to:endpoint, source:entityRef, provenance:refs, binding });
export const coverage = z.strictObject({ lane:semantic, complete:z.boolean(), gaps:z.array(z.strictObject({id, explanation:text, source:entityRef})).max(32), explanation:meta, retention:semantic });
export const traceSummary = z.strictObject({ id, snapshot_id:id, captured_at:timestamp, project_id:id, visibility_scope:id, work:entityRef, root_execution:id, invocation_id:id, run_id:id.nullable(), source_revision:meta, environment:z.array(z.string().max(512)).max(32) });
export const trace = traceSummary.extend({ coverage:z.array(coverage).max(32), execution_bindings:z.array(z.strictObject({execution_id:id,invocation_id:id.nullable(),run_id:id.nullable()})).max(250), executions_complete:z.boolean(), canonical_references:refs });
export const locator = z.strictObject({ id, origin:z.strictObject({contract:z.string().regex(/^[a-f0-9]{64}$/),case:id,record_id:id,item_id:id.nullable(),project_id:id,source_id:id,snapshot_id:id}), target:z.strictObject({contract:semantic,case:id,reference_id:id.nullable(),source_id:id,snapshot_id:id,invocation_id:id,run_id:id.nullable(),record_id:id,visibility_scope:id}) });
export const recordedEvent = z.strictObject({ id, binding, ordinal:z.number().int().nonnegative().nullable(), source_at:timestamp.nullable(), observed_at:timestamp.nullable(), lane:semantic, kind:semantic, summary:text, reasons:z.array(reason).max(32), execution_id:id, invocation_id:id.nullable(), run_id:id.nullable(), references:refs, locator_ids:z.array(id).max(32), previous_id:id.nullable(), next_id:id.nullable() });
export const execution = z.strictObject({ id, binding, execution_class:semantic, registration_state:semantic, invocation:invocation.nullable(), run_id:id.nullable(), relations:z.array(relation).max(80), relations_complete:z.boolean(), references:refs });
export const dimension = z.strictObject({ name:semantic, configured:meta, available:meta, authorized:meta, active:meta, mechanism:meta, self_test:z.strictObject({ok:z.boolean(),reason:meta}).nullable(), vocabulary: z.enum(['ENGINE','PROVISIONAL']) });
export const budget = z.strictObject({ id, policy_id:meta, quantity:z.number().nonnegative().nullable(), unit:semantic, measurement_scope:text, observed:z.number().int().nonnegative().nullable(), active:z.number().int().nonnegative().nullable(), unattributed:z.number().int().nonnegative().nullable(), depth:z.number().int().nonnegative().nullable(), complete:z.boolean(), reported_enforcement:meta, source:entityRef });
export const controls = z.strictObject({ execution_id:id,binding,environment:z.array(z.string().max(512)).max(32),profile_id:meta,dimensions:z.array(dimension).max(32),budgets:z.array(budget).max(16),complete:z.boolean() });
export const controlReceipt = z.strictObject({ id,execution_id:id,binding,environment:z.array(z.string().max(512)).max(32),dimension:semantic,result:semantic,currentness:semantic,validated_at:timestamp.nullable(),mechanism:meta,self_test:z.strictObject({ok:z.boolean(),reason:meta}).nullable(),provenance:refs });
const envelope = <T extends z.ZodType>(data:T) => z.strictObject({schema_version:z.literal('0.1.0'),project_id:id,control_revision:z.string().max(256),generated_at:timestamp,data});
const page = <T extends z.ZodType>(row:T) => z.strictObject({items:z.array(row).max(50),next_cursor:z.string().max(8192).nullable()});
export const wireSchemas = {TraceListResponse:envelope(page(traceSummary)),TraceResponse:envelope(trace),EventListResponse:envelope(page(recordedEvent)),EventResponse:envelope(recordedEvent),ExecutionListResponse:envelope(page(execution)),ExecutionResponse:envelope(execution),ControlsResponse:envelope(controls),ReceiptListResponse:envelope(page(controlReceipt))};
export type Trace = z.infer<typeof trace>;
export type Event = z.infer<typeof recordedEvent>;
export type Execution = z.infer<typeof execution>;
export type Controls = z.infer<typeof controls>;
export type ControlReceipt = z.infer<typeof controlReceipt>;
export type Locator = z.infer<typeof locator>;
export function bindingIssue(b:z.infer<typeof binding>,t:Trace){return b.source_id!==t.id||b.snapshot_id!==t.snapshot_id||b.project_id!==t.project_id?'Trace/snapshot/project binding mismatch':undefined;}
export function eventIssue(e:Event,t:Trace){const owner=t.execution_bindings.find(b=>b.execution_id===e.execution_id);return bindingIssue(e.binding,t)??(!owner||owner.invocation_id!==e.invocation_id||owner.run_id!==e.run_id?'Event execution/invocation/run ownership mismatch':undefined);}
export function executionIssue(e:Execution,t:Trace){
  const owner=t.execution_bindings.find(b=>b.execution_id===e.id);
  return bindingIssue(e.binding,t)??(!owner||owner.invocation_id!==(e.invocation?.id??null)||owner.run_id!==e.run_id?'Invocation/run ownership mismatch':undefined)??(e.run_id!==null&&(!e.invocation||!e.invocation.runs.some(r=>r.id===e.run_id))?'Invocation/run ownership mismatch':undefined)??(e.relations.some(r=>bindingIssue(r.binding,t)||r.from.id!==e.id||r.from.kind!=='execution'||r.source.kind!=='relation_source')?'Relation source/endpoint binding mismatch':undefined);
}
export const executionSchemas = {...wireSchemas,
  TraceListResponse:wireSchemas.TraceListResponse.superRefine((v,c)=>{if(v.data.items.some(t=>t.project_id!==v.project_id||t.visibility_scope!==v.project_id))c.addIssue({code:'custom',message:'Project-only visibility mismatch'});}),
  TraceResponse:wireSchemas.TraceResponse.superRefine((v,c)=>{if(v.data.project_id!==v.project_id||v.data.visibility_scope!==v.project_id)c.addIssue({code:'custom',message:'Project-only visibility mismatch'});}),
};
export const hierarchyKinds = relationKinds.filter(k=>k!=='trace_correlation');
