const routes: Record<string, string> = {
  work: 'work',
  epic: 'work',
  story: 'work',
  ticket: 'work',
  run: 'runs',
  evidence: 'evidence',
  knowledge: 'knowledge',
  decision: 'knowledge',
  fact: 'knowledge',
  assumption: 'knowledge',
  history: 'history',
};
export function entityLink(entity: {
  kind: string;
  id: string;
}): string | undefined {
  const route = routes[entity.kind];
  return route ? `/${route}/${encodeURIComponent(entity.id)}` : undefined;
}
export function detailRoute(
  collection: 'work' | 'runs' | 'evidence' | 'knowledge' | 'history',
  id: string,
) {
  return `/${collection}/${encodeURIComponent(id)}`;
}
