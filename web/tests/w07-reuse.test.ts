import { describe, it, expect } from 'vitest';
import manifest from '../docs/design/w07-reuse.manifest.json';
import { reuseManifestSchema, reuseItemIssue } from '../src/api/preview/journal/reuse';
import { investigationFixture } from '../src/api/preview/investigation/fixtures';
describe('supplied reuse association boundaries', () => {
  const a = reuseManifestSchema.parse(manifest).associations[0];
  it('pins a later packet item and never the earlier retry packet', () => {
    const fixture = investigationFixture(a.target.case);
    expect(reuseItemIssue(fixture.items.filter(i => i.packet_id === a.target.record_id), a)).toBeUndefined();
    expect(reuseItemIssue(fixture.items.filter(i => i.packet_id === 'PKT-Retry'), a)).toBeTruthy();
    expect(fixture.packets.find(p => p.id === a.target.record_id)?.receipts.some(r => r.type === 'BENEFIT')).toBe(false);
  });
  it('rejects duplicate locators, unknown fields and contract substitutions', () => {
    expect(reuseManifestSchema.safeParse({ ...manifest, associations: [a, a] }).success).toBe(false);
    expect(reuseManifestSchema.safeParse({ ...manifest, raw_prompt: 'excluded' }).success).toBe(false);
    for (const field of ['origin', 'target'] as const) {
      expect(reuseManifestSchema.safeParse({ ...manifest, associations: [{ ...a, [field]: { ...a[field], contract: 'a'.repeat(64) } }] }).success).toBe(false);
    }
  });
  it('rejects item/source/packet/section/revision/reference substitutions', () => {
    const item = investigationFixture(a.target.case).items.find(i => i.id === a.target.item_id)!;
    for (const field of ['id', 'packet_id', 'source_id', 'section', 'source_revision'] as const)
      expect(reuseItemIssue([{ ...item, [field]: 'other' }], a)).toBeTruthy();
    expect(reuseItemIssue([{ ...item, reference: { ...item.reference, id: 'J-04' } }], a)).toBeTruthy();
    expect(reuseItemIssue([{ ...item, reference: { ...item.reference, kind: 'evidence_reference' } }], a)).toBeTruthy();
  });
});
