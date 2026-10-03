import type { World } from './types';
export type { World } from './types';
const files = import.meta.glob<World>('./fixtures/F*.json', {
  eager: true,
  import: 'default',
});
export const worlds = Object.values(files).sort(
  (a, b) => Number(a.fixture.slice(1)) - Number(b.fixture.slice(1)),
);
export function selectedWorld() {
  return (
    worlds.find(
      (w) =>
        w.fixture === new URLSearchParams(location.search).get('fixture'),
    ) ?? worlds.find((w) => w.fixture === 'F1')!
  );
}
