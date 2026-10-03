import { z } from 'zod';
export const journalKinds = ['observation', 'hypothesis', 'failed_approach', 'discovery', 'conditional_lesson', 'decision_reference', 'environment_constraint'];
export const applicabilityValues = ['CURRENT', 'HISTORICALLY_VALID', 'STALE_FOR_ENVIRONMENT', 'SUPERSEDED', 'CONTRADICTORY', 'UNCHECKED'];
const identity = z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9._:/-]*$/);
const metadata = z.string().min(1).max(512).nullable();
const utc = z.iso.datetime({ precision: undefined });
const content = z.strictObject({ format: z.string().min(1).max(40), text: z.string().max(32768) });
export const journalReference = z.strictObject({ kind: z.string().min(1).max(64), id: identity, title: z.string().max(512).nullable() });
export const journalEntry = z.strictObject({
    id: identity, kind: z.string().min(1).max(64), title: z.string().min(1).max(512),
    component: metadata, published_at: utc.nullable(), observed_at: utc.nullable(), derived_at: utc.nullable(),
    claim: content, applicability: metadata, conditions: z.array(z.string().max(2048)).max(50), limitations: z.array(z.string().max(2048)).max(50),
    retention_explanation: z.strictObject({ state: z.string().min(1).max(64), text: z.string().max(4096).nullable() }),
    supporting_evidence: z.array(journalReference).max(250), opposing_evidence: z.array(journalReference).max(250),
    origin: z.strictObject({ work: journalReference.nullable(), attempt_id: metadata, invocation: journalReference.nullable(), run_id: metadata, source_revision: metadata, environment: z.array(z.string().max(512)).max(30) }),
    producer: z.strictObject({ id: identity, role: z.string().max(128).nullable() }).nullable(),
    model_id: identity.nullable(), prompt_id: identity.nullable(), prompt_version: identity.nullable(), prompt_digest: z.string().max(256).regex(/^[A-Za-z0-9_-]+:[A-Fa-f0-9]+$/).nullable(),
    canonical_references: z.array(journalReference).max(100),
    relations: z.array(z.strictObject({ relation: z.string().min(1).max(64), target: journalReference })).max(250),
    relations_truncated: z.boolean(),
});
const envelope = <T extends z.ZodType>(data: T) => z.strictObject({ schema_version: z.literal('0.1.0'), project_id: identity, control_revision: z.string().min(1).max(256), generated_at: utc, data });
export const journalSchemas = {
    JournalResponse: envelope(journalEntry),
    JournalListResponse: envelope(z.strictObject({ items: z.array(journalEntry).max(50), next_cursor: z.string().min(1).max(256).nullable(), components: z.array(z.string().min(1).max(512)).max(100), kinds: z.array(z.string().min(1).max(64)).max(100) })),
};
export type JournalEntry = z.infer<typeof journalEntry>;
export type JournalReference = z.infer<typeof journalReference>;
export type JournalList = z.infer<typeof journalSchemas.JournalListResponse>;
export const journalCases = ['story', 'large', 'bounds', 'missing', 'stale', 'contradictory', 'unknown', 'denied', 'not-found', 'malformed', 'refresh-error', 'hostile', 'empty'] as const;
