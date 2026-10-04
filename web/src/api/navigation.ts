import { entityLink } from './links';
import { id } from './schema';
const demoKeys = ['fixture', 'fault', 'catalog', 'recipe', 'seed'];
const journalKeys = ['display', 'panel', 'component', 'component_missing', 'journal_case'];
const comparisonKeys = ['investigation_case', 'a_source', 'b_source', 'a_run', 'b_run', 'a_invocation', 'compare_work', 'compare_tab', 'differences', 'choose', 'source_cursor', 'packet', 'packet_side', 'packet_tab', 'packet_section', 'packet_disposition', 'packet_cursor'];
const evidenceKeys = ['evidence_reference','evidence_source','evidence_artifact','evidence_revision','evidence_tab','evidence_case','evidence_filter','evidence_work','evidence_source_cursor','evidence_artifact_cursor','evidence_excerpt_cursor','evidence_pane'];
const executionKeys = ['execution_case','execution_trace','execution_selected','execution_kind','execution_view','execution_display','execution_lane','execution_filter','execution_cursor','execution_trace_cursor','execution_work','execution_invocation','execution_run','execution_tab','execution_pane','execution_locator','execution_receipt_cursor','execution_control_tab'];
const presentationKeys = ['selected', 'inspector', 'field', 'view', 'focus', 'work_pane'];
const filterKeys = [
  'state',
  'kind',
  'parent',
  'cursor',
  'work',
  'since',
  'until',
];
export const historicalKeys = ['rev', 'revision', 'snapshot'];
export function historicalRequested(params: URLSearchParams) {
  return historicalKeys.some((key) => params.has(key));
}
export function navigationParams(params: URLSearchParams, full = false) {
  const next = new URLSearchParams();
  for (const key of [
    ...(import.meta.env.MODE === 'demo' ? demoKeys : []),
    ...(full && import.meta.env.MODE === 'demo' ? journalKeys : []),
    ...(full && import.meta.env.MODE === 'demo' ? comparisonKeys : []),
    ...(full && import.meta.env.MODE === 'demo' ? evidenceKeys : []),
    ...(full && import.meta.env.MODE === 'demo' ? executionKeys : []),
    ...(full ? [...filterKeys, ...presentationKeys, ...historicalKeys] : []),
  ]) {
    const value = params.get(key);
    if (value) next.set(key, value);
  }
  return next;
}
export function dashboardEntityLink(
  entity: { kind: string; id: string },
  search = '',
  workspace = false,
) {
  const route = entityLink(entity);
  if (!route || !id.safeParse(entity.id).success) return;
  const params = navigationParams(new URLSearchParams(search), workspace);
  if (workspace) {
    params.set('selected', entity.id);
    if (params.has('work_pane') && ['work', 'ticket', 'story', 'epic'].includes(entity.kind))
      params.set('work_pane', 'detail');
    params.delete('inspector');
    params.delete('field');
  }
  return (
    (workspace ? route.slice(0, route.lastIndexOf('/')) : route) +
    (params.size ? '?' + params : '')
  );
}
export function dashboardCopyLink(
  pathname: string,
  search: string,
  origin: string,
) {
  const params = navigationParams(new URLSearchParams(search), true);
  return new URL(pathname + (params.size ? '?' + params : ''), origin).href;
}
