import type { Investigation, Source } from '../../../client/investigation-model';
import type { JournalEntry } from './schema';
export function inspectJournal(record: JournalEntry, source: Source): Investigation {
    const relations = record.relations.map((r, i) => ({ field: `relations.${i}.${r.relation}`, target: r.target }));
    for (const field of ['supporting_evidence', 'opposing_evidence', 'canonical_references'] as const)
        record[field].forEach((target, i) => relations.push({ field: `${field}.${i}`, target }));
    if (record.origin.work)
        relations.push({ field: 'origin.work', target: record.origin.work });
    if (record.origin.invocation)
        relations.push({ field: 'origin.invocation', target: record.origin.invocation });
    return { key: `journal:${record.id}`, id: record.id, kind: 'journal', source, relations, explanations: [], truncated: record.relations_truncated, archived: false, record };
}
