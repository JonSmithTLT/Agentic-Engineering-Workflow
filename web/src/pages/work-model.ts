import type { components } from '../api/types';
export type Work = components['schemas']['Work'];
export function workRoute(params: URLSearchParams) {
  const query = new URLSearchParams({ limit: '100' });
  for (const key of ['state', 'kind', 'parent', 'cursor']) {
    const value = params.get(key);
    if (value) query.set(key, value);
  }
  return '/work?' + query.toString();
}
/** Order only this loaded page using backend parent links. No inferred counts or health. */
export function workTree(items: Work[], collapsed: ReadonlySet<string>) {
  const ids = new Set(items.map((x) => x.id));
  const children = new Map<string, Work[]>();
  for (const item of items)
    if (item.parent_id && ids.has(item.parent_id))
      children.set(item.parent_id, [
        ...(children.get(item.parent_id) ?? []),
        item,
      ]);
  const seen = new Set<string>();
  const rows: { item: Work; depth: number; expandable: boolean }[] = [];
  function visit(item: Work, depth: number) {
    if (seen.has(item.id)) return;
    seen.add(item.id);
    const nested = children.get(item.id) ?? [];
    rows.push({ item, depth, expandable: nested.length > 0 });
    if (!collapsed.has(item.id))
      for (const child of nested) visit(child, depth + 1);
    else {
      const stack = [...nested];
      while (stack.length) {
        const child = stack.pop()!;
        if (seen.has(child.id)) continue;
        seen.add(child.id);
        stack.push(...(children.get(child.id) ?? []));
      }
    }
  }
  for (const item of items)
    if (!item.parent_id || !ids.has(item.parent_id)) visit(item, 0);
  for (const item of items) if (!seen.has(item.id)) visit(item, 0);
  return rows;
}
