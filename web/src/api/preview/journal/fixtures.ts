import type { JournalEntry, JournalReference } from './schema.ts';
export const ref = (id: string, kind = 'journal', title: string | null = null): JournalReference => ({ id, kind, title });
const make = (id: string, kind: string, title: string, time: string | null, claim: string): JournalEntry => ({
    id, kind, title, component: 'parser', published_at: time, observed_at: time, derived_at: null,
    claim: { format: 'plain', text: claim }, applicability: 'UNCHECKED', conditions: [], limitations: ['Fictional example; no live AEW learning is represented.'],
    retention_explanation: { state: 'MISSING', text: null }, supporting_evidence: [], opposing_evidence: [],
    origin: { work: ref('CLANGD-T181', 'work_reference', 'Investigate missing callers'), attempt_id: 'A-2', invocation: null, run_id: 'CLANGD-R-A2-4', source_revision: 'a319-fictional', environment: ['Rocky 8', 'clangd 19'] },
    producer: { id: 'fictional-observer', role: 'investigator' }, model_id: null, prompt_id: null, prompt_version: null, prompt_digest: null,
    canonical_references: [], relations: [], relations_truncated: false,
});
export const story: JournalEntry[] = [
    make('J-01', 'observation', 'clangd shows no callers', '2026-10-02T16:00:00Z', 'The retained observation reported no callers in the loaded index. That did not establish that the function was unused.'),
    make('J-02', 'hypothesis', 'The function might be dead code', '2026-10-02T16:10:00Z', 'Mistaken hypothesis: missing index references were interpreted as absence of callers.'),
    make('J-03', 'failed_approach', 'Removal breaks the generated build', '2026-10-02T16:20:00Z', 'Failed removal: deleting the function broke generated protocol callers. The approach was reverted in this fictional story.'),
    make('J-04', 'discovery', 'The compilation database was stale', '2026-10-02T16:30:00Z', 'New discovery: refreshed compile_commands exposed generated callers that the previous clangd index had omitted.'),
    make('J-05', 'conditional_lesson', 'Refresh compile_commands before judging missing callers', '2026-10-02T16:40:00Z', 'Conditional lesson: refresh the compilation database before using missing clangd references as evidence that a function is unused.'),
    make('J-06', 'decision_reference', 'Generated protocol definitions remain source-controlled', '2026-10-02T16:40:00Z', 'Reference to the canonical fictional decision D-42. This entry does not replace the decision or confer new authority.'),
    make('J-07', 'environment_constraint', 'A lesson with no publication timestamp', null, 'This retained record has no supplied publication timestamp. Its observation date does not determine publication order.'),
];
story[0].relations = [{ relation: 'related_to', target: ref('J-02') }];
story[1].relations = [{ relation: 'contradicted_by', target: ref('J-03') }, { relation: 'related_to', target: ref('J-01') }];
story[2].relations = [{ relation: 'followed_by', target: ref('J-04') }, { relation: 'originated_from', target: ref('J-02') }];
story[3].relations = [{ relation: 'contributed_to', target: ref('J-05') }, { relation: 'originated_from', target: ref('J-03') }];
story[4].relations = [{ relation: 'derived_from', target: ref('J-04') }, { relation: 'derived_from', target: ref('J-03') }, { relation: 'related_to', target: ref('J-02') }, { relation: 'references', target: ref('J-06') }, { relation: 'applies_to', target: ref('CLANGD-T203', 'work_reference', 'Supplied potential applicability: inspect generated protocol callers') }, { relation: 'recalled_for', target: ref('CLANGD-T207', 'work_reference', 'Supplied recall reference: compiler upgrade investigation; no delivery or benefit receipt supplied') }];
story[4].applicability = 'CURRENT';
story[4].conditions = ['clangd 19 with generated protocol callers', 'Refresh compile_commands for the evaluated revision before applying this lesson.'];
story[4].retention_explanation = { state: 'SUPPLIED', text: 'The supplied fictional failure/fix pair supports retaining this conditional lesson.' };
story[4].supporting_evidence = [ref('CLANGD-E871', 'evidence_reference', 'Removal build failure'), ref('CLANGD-E875', 'evidence_reference', 'Refreshed database reveals callers')];
story[4].opposing_evidence = [ref('CLANGD-E880', 'evidence_reference', 'Fresh database can also confirm genuinely unused functions; absence of references alone is insufficient.')];
story[4].producer = { id: 'fictional-distiller', role: 'advisory distillation' };
story[4].model_id = 'fictional-model';
story[4].prompt_id = 'distill';
story[4].prompt_version = 'v2';
story[4].prompt_digest = 'sha256:' + 'a'.repeat(64);
story[4].derived_at = '2026-10-02T16:39:00Z';
story[4].canonical_references = [ref('CLANGD-D42', 'decision_reference', 'Generated protocol definitions remain source-controlled')];
story[5].canonical_references = structuredClone(story[4].canonical_references);
story[6].component = null;
story[6].observed_at = '2026-10-03T12:00:00Z';
export function journalFixture(name: string): JournalEntry[] {
    const entries = structuredClone(story);
    if (name === 'empty')
        return [];
    if (name === 'large')
        return Array.from({ length: 10000 }, (_, i) => {
            const record = structuredClone(entries[i % entries.length]);
            record.id = `L-${String(i).padStart(5, '0')}`;
            record.relations = record.relations.map((r) => r.target.kind === 'journal' ? { ...r, target: { ...r.target, id: `L-${String(Number(r.target.id.slice(2)) - 1).padStart(5, '0')}` } } : r);
            return record;
        });
    const lesson = entries[4];
    if (name === 'bounds') {
        lesson.relations = Array.from({ length: 200 }, (_, i) => ({ relation: 'related_to', target: ref(`BOUND-${i % 23}`, 'reference') }));
        lesson.relations_truncated = true;
    }
    if (name === 'missing') {
        lesson.retention_explanation = { state: 'MISSING', text: null };
        lesson.supporting_evidence = [];
        lesson.opposing_evidence = [];
        lesson.applicability = null;
        lesson.producer = null;
        lesson.canonical_references = [];
    }
    if (name === 'stale')
        lesson.applicability = 'STALE_FOR_ENVIRONMENT';
    if (name === 'contradictory')
        lesson.applicability = 'CONTRADICTORY';
    if (name === 'unknown') {
        lesson.kind = 'FUTURE_JOURNAL_KIND';
        lesson.applicability = 'FUTURE_APPLICABILITY';
        lesson.retention_explanation = { state: 'FUTURE_EXPLANATION', text: null };
        lesson.relations.push({ relation: 'FUTURE_RELATION', target: ref('UNKNOWN-1', 'future_entity') });
    }
    if (name === 'hostile')
        lesson.claim = { format: 'markdown', text: '<script>globalThis.journalAttack=true</script>\n<img src="https://attacker.invalid/journal">\n[unsafe](javascript:alert(1))\n\n**Safe retained text**' };
    return entries;
}
