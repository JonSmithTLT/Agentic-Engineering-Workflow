import type { components } from '../types';
type Envelope = components['schemas']['OverviewResponse'];
export type World = {
  fixture: string;
  name: string;
  contract_version: string;
  contract_sha256: string;
  responses: Record<string, unknown>;
  pages: Record<string, unknown>;
  scenarios: { kind: string; [key: string]: unknown }[];
};
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
      (w) => w.fixture === new URLSearchParams(location.search).get('fixture'),
    ) ?? worlds.find((w) => w.fixture === 'F1')!
  );
}
export function overviewOf(world: World) {
  return world.responses['/overview'] as Envelope;
}
