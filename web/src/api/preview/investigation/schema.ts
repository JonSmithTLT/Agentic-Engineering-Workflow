import { z } from 'zod';
// @ts-expect-error Node's pinned strip-types artifact runner requires the explicit extension.
import { invocation, entityRef, richText, timestamp, id, reason } from '../../schema.ts';
const meta = z.string().max(512).nullable();
const identityMeta = z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9._:/-]*$/).nullable();
const refs = z.array(entityRef).max(250);
export const investigationCases = ['story', 'later-ticket', 'parallel', 'large', 'missing', 'partial', 'contradictory', 'unknown', 'denied', 'not-found', 'historical-unavailable', 'malformed', 'stale', 'refresh-error', 'hostile', 'empty'] as const;
const packetAssociation = z.strictObject({ id, source_id: id, invocation_id: id, run_id: id.nullable() });
export const sourceSummary = z.strictObject({ id, invocation_id: id, work: entityRef, status: z.string().max(64), mode: z.enum(['CURRENT', 'FIXED']), snapshot_id: id.nullable(), captured_at: timestamp.nullable(), visibility_scope: id });
export const comparisonSource = z.strictObject({
  id, invocation, mode: z.enum(['CURRENT', 'FIXED']), snapshot_id: id.nullable(), captured_at: timestamp.nullable(), visibility_scope: id,
  work_revision: meta, source_revision: meta, environment: z.array(z.string().max(512)).max(30),
  model_id: meta, provider: meta, profile_id: meta, card_id: meta, capability_id: meta,
  prompt_id: identityMeta, prompt_version: identityMeta, prompt_digest: z.string().max(256).regex(/^[A-Za-z0-9_-]+:[A-Fa-f0-9]+$/).nullable(),
  evidence_complete: z.boolean(), packets: z.array(packetAssociation).max(250), packets_complete: z.boolean(),
});
export const receipt = z.strictObject({
  id, type: z.string().max(64), state: z.string().max(64), result: meta,
  packet_id: id, source_id: id, invocation_id: id, run_id: id.nullable(), snapshot_id: id.nullable(),
  at: timestamp.nullable(), provenance: refs,
});
export const packet = z.strictObject({
  id, source_id: id, invocation_id: id, run_id: id.nullable(), snapshot_id: id.nullable(),
  prepared_at: timestamp.nullable(), fingerprint: meta, producer: z.strictObject({ id, role: meta }).nullable(),
  policy_id: meta, trigger: meta, source_revision: meta, environment: z.array(z.string().max(512)).max(30),
  sections: z.array(z.strictObject({ id, title: z.string().max(512), count: z.number().int().nonnegative().nullable() })).max(32),
  sections_complete: z.boolean(),
  accounting: z.array(z.strictObject({ unit: z.string().max(64), amount: z.number().nonnegative().nullable(), limit: z.number().nonnegative().nullable(), estimator_id: meta, tokenizer_id: meta })).max(8),
  canonical_references: refs, receipts: z.array(receipt).max(100), receipts_complete: z.boolean(),
});
export const packetItem = z.strictObject({
  id, packet_id: id, source_id: id, section: id, reference: entityRef, source_revision: meta,
  disposition: z.string().max(64), explanation: z.strictObject({ state: z.string().max(64), text: z.string().max(4096).nullable() }),
  excerpt: richText.nullable(), excerpt_scope: meta, excerpt_truncated: z.boolean(),
});
const envelope = <T extends z.ZodType>(data: T) => z.strictObject({ schema_version: z.literal('0.1.0'), project_id: id, control_revision: z.string().max(256), generated_at: timestamp, data });
const page = <T extends z.ZodType>(item: T) => z.strictObject({ items: z.array(item).max(50), next_cursor: z.string().max(8192).nullable() });
export const wireSchemas = {
  ComparisonSourceResponse: envelope(comparisonSource), ComparisonSourceListResponse: envelope(page(sourceSummary)),
  PacketResponse: envelope(packet), PacketItemListResponse: envelope(page(packetItem)),
};
export const investigationSchemas = { ...wireSchemas, PacketItemListResponse: wireSchemas.PacketItemListResponse.superRefine((value, ctx) => {
  let total = 0;
  for (const item of value.data.items) { const size = new TextEncoder().encode(item.excerpt?.text ?? '').length; total += size; if (size > 16384) ctx.addIssue({ code: 'custom', message: 'Excerpt exceeds 16 KiB' }); }
  if (total > 131072) ctx.addIssue({ code: 'custom', message: 'Excerpt page exceeds 128 KiB' });
}) };
export type ComparisonSource = z.infer<typeof comparisonSource>;
export type SourceSummary = z.infer<typeof sourceSummary>;
export type Packet = z.infer<typeof packet>;
export type PacketItem = z.infer<typeof packetItem>;
export type Receipt = z.infer<typeof receipt>;
export type PreviewEnvelope<T> = { schema_version: '0.1.0'; project_id: string; control_revision: string; generated_at: string; data: T };
/** Context-domain bindings are independent of any comparison component. */
export function sourceBindingIssue(source: ComparisonSource) {
  if ((source.mode === 'FIXED') !== (source.snapshot_id !== null)) return 'Snapshot binding mismatch';
  if (source.packets.some(p => p.source_id !== source.id || p.invocation_id !== source.invocation.id || (p.run_id !== null && !source.invocation.runs.some(r => r.id === p.run_id)))) return 'Packet association binding mismatch';
}
export function packetBindingIssue(value: Packet, source: ComparisonSource) {
  const association = source.packets.find(p => p.id === value.id);
  if (!association || value.source_id !== source.id || value.invocation_id !== source.invocation.id || value.run_id !== association.run_id || value.snapshot_id !== source.snapshot_id) return 'Packet binding mismatch';
  if (value.receipts.some(r => r.packet_id !== value.id || r.source_id !== value.source_id || r.invocation_id !== value.invocation_id || r.run_id !== value.run_id || r.snapshot_id !== value.snapshot_id)) return 'Receipt binding mismatch';
}
export const knownReceiptTypes = ['PREPARATION', 'DELIVERY', 'CITATION', 'BENEFIT'];
export const knownReceiptStates = ['RECORDED', 'ACKNOWLEDGED', 'REJECTED', 'EVALUATED', 'UNKNOWN'];
export const knownDispositions = ['INCLUDED', 'OMITTED', 'TRUNCATED'];
export const knownExplanationStates = ['SUPPLIED', 'MISSING', 'UNKNOWN', 'DENIED'];
export { reason };
