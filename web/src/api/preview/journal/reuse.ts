import { z } from 'zod';
import { id } from '../../schema';
import { journalContract } from './registration';
import { investigationContract } from '../investigation/registration';
import type { PacketItem } from '../investigation/schema';

const digest = z.string().regex(/^[a-f0-9]{64}$/);
export const reuseAssociation = z.strictObject({
  id,
  origin: z.strictObject({ contract: digest, case: id, project_id: id, record_id: id }),
  target: z.strictObject({ contract: digest, case: id, source_id: id, snapshot_id: id,
    visibility_scope: id, invocation_id: id, run_id: id.nullable(), record_id: id,
    item_id: id, reference_kind: z.literal('journal'), reference_id: id,
    source_revision: z.string().max(512).nullable(), section: id, cursor: z.string().max(8192).nullable() }),
});
export type ReuseAssociation = z.infer<typeof reuseAssociation>;
export const reuseManifestSchema = z.strictObject({ version: z.literal('1.0'),
  associations: z.array(reuseAssociation).max(50),
}).superRefine((value, ctx) => {
  const seen = new Set<string>();
  for (const a of value.associations) {
    if (seen.has(a.id) || a.origin.contract !== journalContract.sha256 || a.target.contract !== investigationContract.sha256 || a.target.reference_id !== a.origin.record_id)
      ctx.addIssue({ code: 'custom', message: 'Duplicate identity or contract/reference binding mismatch' });
    seen.add(a.id);
  }
});
export function reuseItemIssue(items: PacketItem[], a: ReuseAssociation) {
  const matches = items.filter(i => i.id === a.target.item_id), item = matches[0];
  return matches.length !== 1 || !item || item.packet_id !== a.target.record_id || item.source_id !== a.target.source_id ||
    item.section !== a.target.section || item.reference.kind !== a.target.reference_kind ||
    item.reference.id !== a.target.reference_id || item.source_revision !== a.target.source_revision
    ? 'Context association item binding mismatch or unavailable item.' : undefined;
}
