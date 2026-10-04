import { z } from 'zod';
// @ts-expect-error Explicit extension supports the pinned artifact runner.
import { evidence, entityRef, timestamp, id } from '../../schema.ts';
// @ts-expect-error Explicit extension supports the pinned artifact runner.
import { sha256 } from './digest.ts';
const digest = z.string().regex(/^[a-f0-9]{64}$/), meta = z.string().max(512).nullable();
export const evidenceCases = ['story','large','missing','partial','denied','not-found','historical-unavailable','unknown','malformed','hash-mismatch','binding-mismatch','refresh-error','stale','hostile','empty'] as const;
export const origin = z.strictObject({ contract: digest, case: id, record_id: id, item_id: id.nullable(), kind: z.string().max(64), role: z.string().max(64), evidence_id: id, source_id: id.nullable(), snapshot_id: id.nullable(), visibility_scope: id });
export const association = z.strictObject({ reference_id: id, origin, source_ids: z.array(id).max(50), complete: z.boolean() });
export const sourceSummary = z.strictObject({ id, evidence_id: id, snapshot_id: id, captured_at: timestamp, visibility_scope: id, source_revision: meta, work: entityRef });
export const evidenceSource = sourceSummary.extend({ evidence, canonical_references: z.array(entityRef).max(250), artifacts_complete: z.boolean() });
export const artifact = z.strictObject({ id, source_id: id, evidence_id: id, snapshot_id: id, revision: id, display_name: z.string().max(512).nullable(), media_type: z.string().max(128), encoding: z.string().max(64), full_digest: meta, size_bytes: z.number().int().nonnegative().nullable(), availability: z.string().max(64), explanation: z.string().max(4096).nullable() });
export const excerptWire = z.strictObject({ source_id: id, evidence_id: id, snapshot_id: id, artifact_id: id, artifact_revision: id, cursor: z.string().max(8192).nullable(), text: z.string().max(16384), byte_start: z.number().int().nonnegative(), byte_end: z.number().int().nonnegative(), line_start: z.number().int().positive().nullable(), line_end: z.number().int().positive().nullable(), sha256: digest, truncated: z.boolean(), scope: z.string().max(512), complete_value: z.boolean(), next_cursor: z.string().max(8192).nullable() });
const envelope = <T extends z.ZodType>(data: T) => z.strictObject({ schema_version: z.literal('0.1.0'), project_id: id, control_revision: z.string().max(256), generated_at: timestamp, data });
const page = <T extends z.ZodType>(item: T) => z.strictObject({ items: z.array(item).max(50), next_cursor: z.string().max(8192).nullable() });
export const wireSchemas = { ReferenceResponse: envelope(association), EvidenceSourceListResponse: envelope(page(sourceSummary)), EvidenceSourceResponse: envelope(evidenceSource), ArtifactListResponse: envelope(page(artifact)), ExcerptResponse: envelope(excerptWire) };
export const evidenceSchemas = { ...wireSchemas, ExcerptResponse: wireSchemas.ExcerptResponse.superRefine(({data:v}, ctx) => {
  if (new TextEncoder().encode(v.text).length > 16384 || v.byte_end - v.byte_start !== new TextEncoder().encode(v.text).length || v.byte_end < v.byte_start) ctx.addIssue({code:'custom',message:'Excerpt byte range/bound mismatch'});
  if (sha256(v.text) !== v.sha256) ctx.addIssue({code:'custom',message:'Excerpt integrity mismatch'});
  if ((v.line_start === null) !== (v.line_end === null) || (v.line_start !== null && v.line_end! < v.line_start)) ctx.addIssue({code:'custom',message:'Excerpt line range mismatch'});
}) };
export type Origin = z.infer<typeof origin>;
export type Association = z.infer<typeof association>;
export type EvidenceSource = z.infer<typeof evidenceSource>;
export type Artifact = z.infer<typeof artifact>;
export type Excerpt = z.infer<typeof excerptWire>;
export function excerptIssue(v: Excerpt, s: EvidenceSource, a: Artifact, cursor: string | null) {
  return v.source_id !== s.id || v.evidence_id !== s.evidence_id || v.snapshot_id !== s.snapshot_id || v.artifact_id !== a.id || v.artifact_revision !== a.revision || v.cursor !== cursor || (a.size_bytes !== null && v.byte_end > a.size_bytes) ? 'Excerpt binding/range mismatch' : undefined;
}
export function sourceIssue(s: EvidenceSource) { return s.evidence.id !== s.evidence_id ? 'Evidence identity mismatch' : undefined; }
export const supportedMedia = ['text/plain','text/x-code','text/x-log','text/markdown','application/json'];
