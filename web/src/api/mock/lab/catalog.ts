import { scenarioConfig, scenarioVersion } from './config';
export type ReplayAction =
  | {
      kind: 'refresh';
      effect?:
        | 'normal'
        | 'http'
        | 'network'
        | 'malformed'
        | 'initial304'
        | 'bad304'
        | 'unknown'
        | 'downgrade'
        | 'newer'
        | 'mixed'
        | 'converge'
        | 'hold';
    }
  | { kind: 'advance'; milliseconds: number; visible?: boolean }
  | { kind: 'switch' };
export type Recipe = {
  id: string;
  title: string;
  fixture: string;
  steps: { title: string; action: ReplayAction; expected: string }[];
};
const refresh = (
  title: string,
  effect: Extract<ReplayAction, { kind: 'refresh' }>['effect'],
  expected: string,
) => ({ title, action: { kind: 'refresh' as const, effect }, expected });
export const replayCatalogMarker = 'W01_REPLAY_CATALOG';
export const recipes: Recipe[] = [
  {
    id: 'conditional',
    title: 'Load and conditional recheck',
    fixture: 'F1',
    steps: [
      refresh(
        'Recheck unchanged projections',
        'normal',
        '304 retains generation time and revision',
      ),
    ],
  },
  {
    id: 'initial-304',
    title: 'Initial 304 without data',
    fixture: 'F1',
    steps: [
      refresh(
        'Retry after invalid initial 304',
        'normal',
        'No stale nonexistent data; retry recovers',
      ),
    ],
  },
  {
    id: 'validator',
    title: 'Mismatched validator',
    fixture: 'F1',
    steps: [
      refresh(
        'Return anomalous 304',
        'bad304',
        'Browser ETag observation; cached payload is retained',
      ),
    ],
  },
  {
    id: 'failed-refresh',
    title: 'Failed and malformed refresh',
    fixture: 'F1',
    steps: [
      refresh(
        'Return HTTP 500',
        'http',
        'STALE / DISCONNECTED with last-known-good content',
      ),
      refresh(
        'Return malformed JSON shape',
        'malformed',
        'Exact validation paths; valid content retained',
      ),
      refresh(
        'Recover',
        'normal',
        'Successful revalidation restores currentness',
      ),
    ],
  },
  {
    id: 'initial-http',
    title: 'Initial HTTP failure',
    fixture: 'F1',
    steps: [
      refresh(
        'Recover from HTTP error',
        'normal',
        'Initial failure is LOAD ERROR, then valid data',
      ),
    ],
  },
  {
    id: 'initial-network',
    title: 'Initial network failure',
    fixture: 'F1',
    steps: [
      refresh(
        'Recover connection',
        'normal',
        'Network failure is distinct from HTTP failure',
      ),
    ],
  },
  {
    id: 'capability',
    title: 'Capability downgrade',
    fixture: 'F1',
    steps: [
      refresh(
        'Disable Work',
        'downgrade',
        'Work unavailable; disabled reads stop',
      ),
      refresh('Recheck disabled view', 'normal', 'No Work request'),
    ],
  },
  {
    id: 'transient-mixed',
    title: 'Transient mixed revisions',
    fixture: 'F1',
    steps: [
      refresh(
        'Keep project old; advance other projections',
        'mixed',
        'UPDATING',
      ),
      {
        title: 'Advance 10 visible seconds',
        action: { kind: 'advance', milliseconds: 10000 },
        expected: 'No persistent warning',
      },
      refresh(
        'Converge revisions',
        'converge',
        'CURRENT; divergence clock clears',
      ),
    ],
  },
  {
    id: 'persistent-mixed',
    title: 'Visible divergence and hidden pause',
    fixture: 'F1',
    steps: [
      refresh('Create mixed revisions', 'mixed', 'UPDATING'),
      {
        title: 'Advance 20 visible seconds',
        action: { kind: 'advance', milliseconds: 20000 },
        expected: 'No warning yet',
      },
      {
        title: 'Hide replay document',
        action: { kind: 'advance', milliseconds: 0, visible: false },
        expected: 'Visible divergence time pauses',
      },
      {
        title: 'Advance 60 hidden seconds',
        action: { kind: 'advance', milliseconds: 60000 },
        expected: 'Still no persistent warning',
      },
      {
        title: 'Show replay document',
        action: { kind: 'advance', milliseconds: 0, visible: true },
        expected: 'Immediate explicit revalidation',
      },
      {
        title: 'Advance 10 visible seconds',
        action: { kind: 'advance', milliseconds: 10000 },
        expected: 'Mixed revisions persist',
      },
      refresh('Converge', 'converge', 'Warning clears'),
    ],
  },
  {
    id: 'late-session',
    title: 'Old response after session switch',
    fixture: 'F1',
    steps: [
      refresh(
        'Hold current Overview response',
        'hold',
        'Pending response; no commit yet',
      ),
      {
        title: 'Switch to another authored project',
        action: { kind: 'switch' },
        expected: 'New bootstrap; old content removed',
      },
      refresh('Recheck new scope', 'normal', 'No old payload or validator'),
    ],
  },
  {
    id: 'unknown',
    title: 'Future semantic value',
    fixture: 'F1',
    steps: [
      refresh(
        'Return a future Work state',
        'unknown',
        'Valid shape; raw unknown-value warning',
      ),
    ],
  },
  {
    id: 'hostile',
    title: 'Hostile content world',
    fixture: 'F8',
    steps: [
      refresh(
        'Recheck hostile-content fixtures',
        'normal',
        'Escaped/safe display; no remote resources',
      ),
    ],
  },
  {
    id: 'large-work',
    title: 'Large active Work list',
    fixture: 'F6',
    steps: [
      refresh(
        'Recheck bounded Work list',
        'normal',
        'Loaded-page bounds and virtualization retained',
      ),
    ],
  },
  {
    id: 'large-history',
    title: 'Bounded history pagination',
    fixture: 'F7',
    steps: [
      refresh(
        'Recheck history window',
        'normal',
        'Bounded page; no full archive crawl',
      ),
    ],
  },
];
export function readScenario(search: string) {
  const params = new URLSearchParams(search);
  if (!params.has('recipe')) return undefined;
  const result = scenarioConfig.safeParse({
    catalog: params.get('catalog'),
    recipe: params.get('recipe'),
    fixture: params.get('fixture'),
    seed: Number(params.get('seed')),
  });
  if (!result.success) return undefined;
  const recipe = recipes.find(
    (r) => r.id === result.data.recipe && r.fixture === result.data.fixture,
  );
  return recipe ? { ...result.data, definition: recipe } : undefined;
}
export function scenarioLink(recipe: Recipe, seed = 1, base = location.href) {
  const url = new URL(base);
  url.search = '';
  for (const [name, value] of Object.entries({
    catalog: scenarioVersion,
    recipe: recipe.id,
    fixture: recipe.fixture,
    seed: String(seed),
  }))
    url.searchParams.set(name, value);
  return url.href;
}
