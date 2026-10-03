import { z } from 'zod';
const item = z.object({
  id: z.string().min(1).max(512),
  state: z.string().max(256).nullable(),
});
export const savedView = z.object({
  project: z.string().max(512),
  scope: z.string().max(4096),
  revision: z.string().regex(/^(0|[1-9][0-9]*)$/),
  at: z.iso.datetime(),
  items: z.array(item).max(100),
});
export type SavedView = z.infer<typeof savedView>;
const savedViews = z.array(savedView).max(20);
const key = 'aew-dashboard-view-memory-v1';
export function readView(
  storage: Storage,
  project: string,
  scope: string,
): SavedView | undefined {
  const raw = storage.getItem(key);
  if (!raw || raw.length > 2_000_000) return;
  try {
    const parsed = savedViews.safeParse(JSON.parse(raw));
    return parsed.success
      ? parsed.data.find((v) => v.project === project && v.scope === scope)
      : undefined;
  } catch {
    return;
  }
}
export function rememberView(storage: Storage, view: SavedView) {
  const raw = storage.getItem(key);
  let views: SavedView[] = [];
  try {
    if (raw && raw.length <= 2_000_000) {
      const parsed = savedViews.safeParse(JSON.parse(raw));
      if (parsed.success) views = parsed.data;
    }
  } catch {
    /* Empty baseline for malformed storage. */
  }
  const valid = savedView.parse(view);
  const prior = views.find(
    (v) => v.project === view.project && v.scope === view.scope,
  );
  if (prior && BigInt(prior.revision) > BigInt(view.revision)) return;
  storage.setItem(
    key,
    JSON.stringify(
      [
        valid,
        ...views.filter(
          (v) => v.project !== view.project || v.scope !== view.scope,
        ),
      ].slice(0, 20),
    ),
  );
}
export function clearViews(storage: Storage) {
  storage.removeItem(key);
}
export function compareView(prior: SavedView, current: SavedView) {
  if (BigInt(current.revision) < BigInt(prior.revision))
    return { older: true, changes: [] };
  const states = new Map(prior.items.map((v) => [v.id, v.state]));
  return {
    older: false,
    changes: current.items.flatMap((v) =>
      !states.has(v.id)
        ? [{ id: v.id, from: undefined, to: v.state }]
        : states.get(v.id) !== v.state
          ? [{ id: v.id, from: states.get(v.id), to: v.state }]
          : [],
    ),
  };
}
