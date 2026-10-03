import {
  ticketStates,
  parentStates,
  invocationStatuses,
  harnessStatuses,
  evidenceResults,
  evidenceCurrentness,
  trustSources,
  workStates,
} from '../api/vocabulary';
import type { z } from 'zod';
import { responseSchemas } from '../api/schema';
import type { Projection } from '../api/transport';
export type EntityKind =
  | 'work'
  | 'invocation'
  | 'evidence'
  | 'knowledge'
  | 'history'
  | 'health'
  | 'attention'
  | 'integrity'
  | 'capability';
export type Reason = { code: string; message: string | null };
export type Source = Projection<{
  schema_version: string;
  project_id: string;
  control_revision: string;
  generated_at: string;
  data?: unknown;
}>;
export type Relation = {
  field: string;
  target: { id: string; kind: string; title?: string | null };
};
export type Explanation = {
  field: string;
  value: string;
  bound: boolean;
  reasons: Reason[];
  sections: { name: string; reasons: Reason[] }[];
};
export type Investigation = {
  key: string;
  id: string;
  kind: EntityKind;
  source: Source;
  explanations: Explanation[];
  relations: Relation[];
  truncated: boolean;
  archived: boolean;
  record: unknown;
  failed?: boolean;
};
type Work = z.infer<typeof responseSchemas.WorkResponse>['data'];
type Invocation = z.infer<typeof responseSchemas.InvocationResponse>['data'];
type Evidence = z.infer<typeof responseSchemas.EvidenceResponse>['data'];
type Knowledge = z.infer<typeof responseSchemas.KnowledgeResponse>['data'];
type History = z.infer<typeof responseSchemas.HistoryResponse>['data'];
export function historyTargetKind(relation: string) {
  if (relation === 'invocations') return 'invocation';
  if (relation === 'evidence') return 'evidence';
  if (['depends_on', 'moved_to', 'audit_finding'].includes(relation))
    return 'history';
  return 'reference';
}
export function investigate(
  kind: EntityKind,
  record: unknown,
  source: Source,
  fallbackId: string = kind,
): Investigation {
  const relations: Relation[] = [],
    explanations: Explanation[] = [];
  let id = fallbackId,
    truncated = false,
    archived = kind === 'history';
  const add = (
    field: string,
    value: unknown,
    reasons: Reason[] = [],
    bound = false,
    sections: Explanation['sections'] = [],
  ) =>
    explanations.push({
      field,
      value:
        value === null || value === undefined ? 'Not supplied' : String(value),
      reasons,
      bound,
      sections,
    });
  const refs = (field: string, values: Relation['target'][]) =>
    values.forEach((target) => relations.push({ field, target }));
  if (kind === 'work') {
    const r = record as Work;
    id = r.id;
    archived = r.archived;
    truncated = r.children_truncated;
    const sections = [{ name: 'blocked_by', reasons: r.blocked_by }];
    add('state', r.state, r.reasons, false, sections);
    add('integration.status', r.integration?.status, r.reasons);
    add('has_attention', r.has_attention, r.reasons);
    if (r.parent_id) refs('parent_id', [{ id: r.parent_id, kind: 'work' }]);
    refs(
      'children',
      r.children.map((id) => ({ id, kind: 'work' })),
    );
    refs('related', r.related);
  } else if (kind === 'invocation') {
    const r = record as Invocation;
    id = r.id;
    add('status', r.status, r.reasons);
    refs('work', [r.work]);
    refs('evidence', r.evidence);
    r.runs.forEach((run, index) => add(`runs.${index}.status`, run.status));
  } else if (kind === 'evidence') {
    const r = record as Evidence;
    id = r.id;
    const sections = [
      { name: 'findings', reasons: r.findings },
      { name: 'deviations', reasons: r.deviations },
    ];
    add('result', r.result, [], false, sections);
    add('currentness', r.currentness, [], false, sections);
    add('requires_disposition', r.requires_disposition, [], false, sections);
    refs('subject', [r.subject]);
    refs('provenance', r.provenance);
    refs('bindings.producer.invocation', [
      { id: r.bindings.producer.invocation, kind: 'invocation' },
    ]);
    if (r.bindings.producer.run)
      refs('bindings.producer.run', [
        { id: r.bindings.producer.run, kind: 'harness_run' },
      ]);
  } else if (kind === 'knowledge') {
    const r = record as Knowledge;
    id = r.id;
    add('state', r.state, r.reasons);
    refs('provenance', r.provenance);
  } else if (kind === 'history') {
    const r = record as History;
    id = r.id;
    add('state', r.state);
    add('source', r.source);
    truncated = !!r.annotations_next_cursor;
    Object.entries(r.links).forEach(([rel, ids]) =>
      refs(
        `links.${rel}`,
        ids.map((id) => ({ id, kind: historyTargetKind(rel) })),
      ),
    );
    r.annotations.forEach((a, index) => {
      if (a.object)
        refs(`annotations.${index}.object`, [
          {
            id: a.object,
            kind: 'reference', // Annotation.object has no target-kind field in 0.1.2.
          },
        ]);
      if (a.decision)
        refs(`annotations.${index}.decision`, [
          { id: a.decision, kind: 'knowledge' },
        ]);
    });
  } else {
    const r = record as {
      id?: string;
      status?: string;
      state?: string;
      severity?: string;
      reasons: Reason[];
      subject?: Relation['target'];
      last_audit?: Relation['target'] | null;
    };
    id = r.id ?? fallbackId;
    const field =
      kind === 'capability'
        ? 'state'
        : kind === 'attention'
          ? 'severity'
          : 'status';
    add(
      field,
      r[field as 'state' | 'severity' | 'status'],
      r.reasons,
      kind === 'health' || kind === 'capability',
    );
    if (r.subject) refs('subject', [r.subject]);
    if (r.last_audit) refs('last_audit', [r.last_audit]);
  }
  return {
    key: kind + ':' + id,
    id,
    kind,
    source,
    explanations,
    relations,
    truncated,
    archived,
    record,
  };
}
export function inspectionFieldValid(field: string | null) {
  return (
    field === null ||
    [
      'state',
      'status',
      'source',
      'severity',
      'result',
      'currentness',
      'requires_disposition',
      'has_attention',
      'integration.status',
    ].includes(field) ||
    /^runs\.(0|[1-9][0-9]{0,2})\.status$/.test(field)
  );
}

/** Vocabulary recognition is display metadata, never a workflow conclusion. */
export function knownExplanationValues(
  kind: EntityKind,
  field: string,
  record: unknown,
): readonly string[] {
  if (kind === 'work') {
    if (field === 'state')
      return (record as Work).kind === 'ticket' ? ticketStates : parentStates;
    if (field === 'has_attention') return ['true', 'false'];
    if (field === 'integration.status')
      return ['prepared', 'publishing', 'conflict', 'superseded'];
  }
  if (kind === 'invocation')
    return field === 'status' ? invocationStatuses : harnessStatuses;
  if (kind === 'evidence')
    return field === 'result'
      ? evidenceResults
      : field === 'currentness'
        ? evidenceCurrentness
        : ['true', 'false'];
  if (kind === 'history') return field === 'source' ? trustSources : workStates;
  if (kind === 'health') return ['HEALTHY', 'DEGRADED', 'UNHEALTHY', 'UNKNOWN'];
  if (kind === 'capability')
    return ['AVAILABLE', 'UNAVAILABLE', 'UNSUPPORTED', 'UNKNOWN'];
  return [];
}
