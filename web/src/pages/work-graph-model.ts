import type { Work } from './work-model';
export const graphCard = {
  width: 236,
  height: 116,
  column: 294,
  row: 144,
  inset: 28,
} as const;
export type GraphNode = {
  id: string;
  item?: Work;
  parent?: string | null;
  children: string[];
  x: number;
  y: number;
};
export function workGraph(
  items: Work[],
  collapsed: ReadonlySet<string>,
  focus = '',
) {
  const nodes = new Map<string, GraphNode>();
  for (const item of items)
    nodes.set(item.id, {
      id: item.id,
      item,
      parent: item.parent_id,
      children: [],
      x: 0,
      y: 0,
    });
  for (const item of items)
    if (item.parent_id) {
      if (!nodes.has(item.parent_id))
        nodes.set(item.parent_id, {
          id: item.parent_id,
          children: [],
          x: 0,
          y: 0,
        });
      nodes.get(item.parent_id)!.children.push(item.id);
    }
  const scope = new Set<string>();
  function collect(id: string) {
    if (scope.has(id)) return;
    scope.add(id);
    for (const child of nodes.get(id)?.children ?? []) collect(child);
  }
  if (focus && nodes.has(focus)) collect(focus);
  else if (!focus) for (const id of nodes.keys()) scope.add(id);
  const hidden = new Set<string>();
  for (const id of collapsed)
    if (scope.has(id)) {
      const seen = new Set([id]);
      function hide(parent: string) {
        for (const child of nodes.get(parent)?.children ?? []) {
          if (seen.has(child)) continue;
          seen.add(child);
          if (scope.has(child) && child !== focus) hidden.add(child);
          hide(child);
        }
      }
      hide(id);
    }
  const visible = new Set([...scope].filter((id) => !hidden.has(id)));
  const seen = new Set<string>();
  let row = graphCard.inset;
  function place(id: string, depth: number) {
    const node = nodes.get(id)!;
    if (seen.has(id)) return node.y;
    seen.add(id);
    node.x = graphCard.inset + depth * graphCard.column;
    node.y = row;
    const ys: number[] = [];
    for (const child of node.children)
      if (visible.has(child) && !seen.has(child))
        ys.push(place(child, depth + 1));
    if (ys.length) node.y = (ys[0] + ys.at(-1)!) / 2;
    else row += graphCard.row;
    return node.y;
  }
  if (focus && visible.has(focus)) place(focus, 0);
  else {
    for (const id of visible) {
      const parent = nodes.get(id)!.parent;
      if (!parent || !visible.has(parent)) {
        place(id, 0);
        row += 20;
      }
    }
    // Cyclic references without a root still get one bounded layout per ID.
    for (const id of visible)
      if (!seen.has(id)) {
        place(id, 0);
        row += 20;
      }
  }
  const placed = [...visible].map((id) => nodes.get(id)!);
  const edges = placed.flatMap((child) =>
    child.parent && visible.has(child.parent)
      ? [{ parent: nodes.get(child.parent)!, child }]
      : [],
  );
  return {
    nodes: placed,
    edges,
    choices: [...nodes.values()],
    focusMissing: !!focus && !nodes.has(focus),
    width: Math.max(
      320,
      ...placed.map((node) => node.x + graphCard.width + graphCard.inset),
    ),
    height: Math.max(
      180,
      ...placed.map((node) => node.y + graphCard.height + graphCard.inset),
    ),
  };
}
