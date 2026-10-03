const routes: Record<string, string> = {
  work: 'work',
  epic: 'work',
  story: 'work',
  ticket: 'work',
  invocation: 'runs',
  evidence: 'evidence',
  knowledge: 'knowledge',
  decision: 'knowledge',
  fact: 'knowledge',
  assumption: 'knowledge',
  history: 'history',
  audit: 'history',
};
export function entityLink(entity: {
  kind: string;
  id: string;
}): string | undefined {
  const route = Object.hasOwn(routes, entity.kind)
    ? routes[entity.kind]
    : undefined;
  return route ? `/${route}/${encodeURIComponent(entity.id)}` : undefined;
}
export function detailRoute(
  collection: 'work' | 'runs' | 'evidence' | 'knowledge' | 'history',
  id: string,
) {
  return `/${collection}/${encodeURIComponent(id)}`;
}
