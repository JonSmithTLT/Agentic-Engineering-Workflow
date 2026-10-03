import { entityLink } from './links';
import { id } from './schema';
const demoKeys = ['fixture', 'fault', 'catalog', 'recipe', 'seed'];
const presentationKeys = ['selected', 'inspector', 'field', 'view', 'focus'];
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
