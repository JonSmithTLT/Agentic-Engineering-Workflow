import type { ComparisonSource, Packet, PacketItem } from './schema';
const ref = (id: string, kind = 'evidence_reference', title: string | null = null) => ({ id, kind, title });
export function investigationFixture(name = 'story') {
  const sources: ComparisonSource[] = [], packets: Packet[] = [], items: PacketItem[] = [];
  for (const [index, label, status, at] of [[1, 'Removal', 'FAILED', '16:20'], [2, 'Retry', 'COMPLETED', '16:38'], [3, 'Later', 'COMPLETED', '17:20']] as const) {
    const source = `SRC-${label}`, invocation = `CLANGD-INV-${label}`, run = index === 1 ? 'CLANGD-R-A2-2' : index === 2 ? 'CLANGD-R-A2-4' : 'CLANGD-R-LATER', packet = `PKT-${label}`;
    const sourceRecord: ComparisonSource = {
      id: source, mode: 'FIXED', snapshot_id: `SNAP-${label}`, captured_at: `2026-10-02T${at}:00Z`, visibility_scope: 'fictional-authorized',
      invocation: { id: invocation, role: 'investigator', status: 'completed', work: ref(index === 3 ? 'CLANGD-T203' : 'CLANGD-T181', 'work_reference', index === 3 ? 'Later caller investigation' : 'Investigate missing callers'), created_at: `2026-10-02T${index === 1 ? '16:15' : index === 2 ? '16:32' : '17:00'}:00Z`,
        runs: [{ id: run, harness: 'fictional-harness', launched_at: `2026-10-02T${index === 1 ? '16:16' : index === 2 ? '16:34' : '17:01'}:00Z`, kind: 'launch', status: 'ended_with_evidence', authority: `Supplied fictional run record; ${status.toLowerCase()} outcome described in invocation summary` }],
        summary: { format: 'plain', text: index === 1 ? 'Removal broke generated protocol callers; the change was reverted.' : index === 2 ? 'After refreshing compile_commands, generated callers were identified and the corrected build passed. The record reports success; it does not establish which difference caused it.' : 'Later investigation received a packet containing the published conditional lesson. No evaluated benefit is supplied.' },
        evidence: [ref(index === 1 ? 'CLANGD-E871' : 'CLANGD-E875')], reasons: [] },
      work_revision: 'plan-3', source_revision: index === 1 ? 'stale-db-fictional' : 'refreshed-db-fictional', environment: ['Rocky 8', 'clangd 19'],
      model_id: 'fictional-model', provider: 'fictional-provider', profile_id: 'investigation-v1', card_id: null, capability_id: 'generated-callers-v1', prompt_id: 'investigate', prompt_version: 'v1', prompt_digest: 'sha256:' + 'a'.repeat(64),
      evidence_complete: true, packets: [{ id: packet, source_id: source, invocation_id: invocation, run_id: run }], packets_complete: true,
    };
    sources.push(sourceRecord);
    const prepared = `2026-10-02T${index === 1 ? '16:15' : index === 2 ? '16:33' : '17:00'}:00Z`;
    const record: Packet = { id: packet, source_id: source, invocation_id: invocation, run_id: run, snapshot_id: sourceRecord.snapshot_id, prepared_at: prepared,
      fingerprint: `fictional-fingerprint-${label}`, producer: { id: 'fictional-context-router', role: 'preparation' }, policy_id: 'context-v1', trigger: 'WORK_START', source_revision: sourceRecord.source_revision, environment: sourceRecord.environment,
      sections: [{ id: 'current', title: 'Current work and constraints', count: 1 }, { id: 'evidence', title: 'Evidence and discovery', count: index === 1 ? 1 : 2 }, { id: 'recall', title: 'Historical recall', count: index === 3 ? 1 : 0 }], sections_complete: true,
      accounting: [{ unit: 'TOKENS', amount: index === 1 ? 980 : 1420, limit: 4000, estimator_id: 'fictional-estimator-v1', tokenizer_id: 'fictional-tokenizer' }, { unit: 'BYTES', amount: 4200, limit: 16000, estimator_id: 'fixture-supplied', tokenizer_id: null }],
      canonical_references: [ref('CLANGD-D42', 'decision_reference', 'Generated protocol definitions remain source-controlled')],
      receipts: [{ id: `RECEIPT-${label}-PREP`, type: 'PREPARATION', state: 'RECORDED', result: null, packet_id: packet, source_id: source, invocation_id: invocation, run_id: run, snapshot_id: sourceRecord.snapshot_id, at: prepared, provenance: [ref(`PREP-SOURCE-${label}`, 'receipt_reference')] }], receipts_complete: true,
    };
    if (index > 1) record.receipts.push({ ...record.receipts[0], id: `RECEIPT-${label}-DELIVERY`, type: 'DELIVERY', state: 'ACKNOWLEDGED', at: `2026-10-02T${index === 2 ? '16:34' : '17:01'}:00Z`, provenance: [ref(`DELIVERY-SOURCE-${label}`, 'receipt_reference')] });
    if (index === 2) record.receipts.push({ ...record.receipts[0], id: 'RECEIPT-Retry-CITATION', type: 'CITATION', state: 'RECORDED', at: '2026-10-02T16:38:00Z', result: 'Output explicitly cites CLANGD-E875.', provenance: [ref('CLANGD-E875')] });
    packets.push(record);
    const add = (identity: string, section: string, text: string, disposition = 'INCLUDED', kind = 'evidence_reference') => items.push({ id: `${packet}-${identity}`, packet_id: packet, source_id: source, section, reference: ref(identity, kind), source_revision: sourceRecord.source_revision, disposition, explanation: { state: 'SUPPLIED', text: 'Explicitly selected by the fictional context policy for this investigation.' }, excerpt: disposition === 'OMITTED' ? null : { format: 'plain', text }, excerpt_scope: disposition === 'OMITTED' ? null : 'Supplied fixture excerpt only; not the entire authoritative record.', excerpt_truncated: disposition === 'TRUNCATED' });
    add('CLANGD-D42', 'current', 'Generated protocol definitions remain source-controlled.', 'INCLUDED', 'decision_reference');
    if (index === 1) add('J-02', 'evidence', 'Mistaken hypothesis: missing index references suggest dead code.', 'INCLUDED', 'journal');
    else { add('CLANGD-E875', 'evidence', 'Refreshed compile_commands reveals generated callers.'); add('J-04', 'evidence', 'The compilation database was stale.', 'INCLUDED', 'journal'); }
    if (index === 3) add('J-05', 'recall', 'Refresh compile_commands before judging missing callers. Published 2026-10-02T16:40:00Z.', 'INCLUDED', 'journal');
  }
  if (name === 'parallel') { sources[1].invocation.summary.text = 'A second agent investigated the same work with refreshed compilation data; conclusions are supplied independently.'; sources[1].model_id = 'fictional-model-B'; }
  if (name === 'missing') { sources[1].model_id = null; packets[1].receipts = []; packets[1].accounting = []; items.forEach(i => { i.explanation = { state: 'MISSING', text: null }; i.excerpt = null; }); }
  if (name === 'partial') { sources[1].evidence_complete = false; sources[1].packets_complete = false; packets[1].receipts_complete = false; packets[1].sections_complete = false; items[2].disposition = 'OMITTED'; items[2].excerpt = null; items[3].disposition = 'TRUNCATED'; items[3].excerpt_truncated = true; }
  if (name === 'contradictory') packets[1].receipts.push({ ...packets[1].receipts[1], id: 'RECEIPT-CONTRADICTORY', state: 'REJECTED', result: 'Conflicting delivery receipt supplied; no resolution supplied.' });
  if (name === 'unknown') { sources[1].invocation.status = 'FUTURE_STATUS'; packets[1].receipts[0].type = 'FUTURE_RECEIPT'; items[2].disposition = 'FUTURE_DISPOSITION'; items[2].explanation.state = 'FUTURE_EXPLANATION'; }
  if (name === 'malformed') packets[1].receipts[0].source_id = 'WRONG-SOURCE';
  if (name === 'hostile') items[2].excerpt = { format: 'markdown', text: '<script>globalThis.w04Attack=true</script>\n<img src="https://attacker.invalid/w04">\n\n[bad](javascript:alert(1))\n\n**Safe supplied excerpt**' };
  if (name === 'stale' || name === 'refresh-error') { sources[1].mode = 'CURRENT'; sources[1].snapshot_id = null; packets[1].snapshot_id = null; packets[1].receipts.forEach(r => r.snapshot_id = null); }
  if (name === 'large') {
    for (let i = 0; i < 1000; i++) sources.push({ ...structuredClone(sources[i % 2]), id: `L-${String(i).padStart(4, '0')}`, packets: [] });
    const seed = items.find(item => item.packet_id === 'PKT-Retry' && item.reference.id === 'CLANGD-E875')!;
    for (let i = 0; i < 120; i++) items.push({ ...structuredClone(seed), id: `ITEM-${String(i).padStart(4, '0')}`, excerpt: { format: 'plain', text: 'Bounded page sample. '.repeat(50) } });
    packets[1].sections[1].count = 122;
  }
  if (name === 'empty') return { sources: [], packets: [], items: [] };
  return { sources, packets, items };
}
