import { ReplayEngine } from './lab/engine';
import { readScenario } from './lab/catalog';
import { worlds, selectedWorld } from './worlds';
export const httpDemo = document.querySelector('meta[name="aew-demo-transport"]')?.getAttribute('content') === 'http';
const scenario = httpDemo ? undefined : readScenario(location.search);
export const replay = scenario ? new ReplayEngine(scenario.definition, scenario.seed, worlds.find((w) => w.fixture === scenario.fixture)!) : undefined;
export async function initializeDemo() {
  if (replay) await replay.start();
  else {
    const { transport } = await import('../transport');
    transport.reset({ ...transport.context.identity, mode: 'demo', dataset: selectedWorld().fixture });
  }
}
