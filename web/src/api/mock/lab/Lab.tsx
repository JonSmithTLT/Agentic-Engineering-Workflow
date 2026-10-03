import { useEffect, useState, useSyncExternalStore } from 'react';
import { acceptedContract } from '../../registry';
import { journalContract } from '../../preview/journal/registration';
import { journalEnvelope } from '../../preview/journal/projector';
import { story } from '../../preview/journal/fixtures';
import { transport } from '../../transport';
import { worlds, selectedWorld } from '../worlds';
import { replay } from '../browser';
import { recipes, scenarioLink } from './catalog';
import { validateInput } from './validation';
const noSubscribe = () => () => {};
const noSnapshot = () => 0;
export default function Lab({ tab }: { tab: string }) {
  useSyncExternalStore(
    replay?.subscribe ?? noSubscribe,
    replay?.snapshot ?? noSnapshot,
  );
  const generation = useSyncExternalStore(
    transport.subscribe,
    transport.snapshot,
  );
  const [recipeId, setRecipeId] = useState(replay?.recipe.id ?? 'conditional');
  const [seed, setSeed] = useState(replay?.seed ?? 1);
  const [model, setModel] = useState('OverviewResponse');
  const [contractId, setContractId] = useState('dashboard-api');
  const contract = contractId === 'journal-preview' ? journalContract : acceptedContract;
  const [text, setText] = useState('');
  const [result, setResult] = useState<ReturnType<typeof validateInput>>();
  const [message, setMessage] = useState('');
  const session = transport.context.generation;
  useEffect(() => {
    setText('');
    setResult(undefined);
  }, [session]);
  void generation;
  const recipe = recipes.find((r) => r.id === recipeId)!;
  const state = replay?.state;
  return (
    <div role="tabpanel" aria-label={tab} className="lab-panel">
      {tab === 'Scenarios' ? (
        <>
          <h3>Scenario Lab</h3>
          {new URLSearchParams(location.search).has('recipe') && !replay && (
            <p role="alert">
              Replay configuration is invalid or unsupported. Normal demo
              browsing is active.
            </p>
          )}
          <p>
            Demo-only authored harness. Manual replay disables interval polling.
            Normal demo browsing uses real polling.
          </p>
          <label>
            Replay recipe
            <select
              value={recipeId}
              onChange={(e) => setRecipeId(e.target.value)}
            >
              {recipes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title} · {r.fixture}
                </option>
              ))}
            </select>
          </label>
          <label>
            Seed
            <input
              type="number"
              min="0"
              max="4294967295"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </label>
          <button
            onClick={() => location.assign(scenarioLink(recipe, seed))}
            disabled={!Number.isInteger(seed) || seed < 0 || seed > 4294967295}
          >
            Start replay
          </button>
          <button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(scenarioLink(recipe, seed));
                setMessage('Scenario link copied');
              } catch {
                setMessage(scenarioLink(recipe, seed));
              }
            }}
          >
            Copy scenario link
          </button>
          <button
            onClick={() => {
              const url = new URL(location.href);
              for (const key of ['recipe', 'catalog', 'seed'])
                url.searchParams.delete(key);
              location.assign(url);
            }}
          >
            Return to normal demo
          </button>
          {replay && state && (
            <>
              <p role="status">
                <strong>Manual replay</strong> · {replay.recipe.title} · seed{' '}
                {replay.seed} · step {state.step}/{replay.recipe.steps.length} ·
                clock {state.milliseconds} ms · simulated{' '}
                {state.visible ? 'visible' : 'hidden'}
              </p>
              <button
                onClick={() => void replay?.next()}
                disabled={
                  state.busy || state.step >= replay.recipe.steps.length
                }
              >
                Next step
              </button>
              <button onClick={() => void replay?.reset()}>Reset</button>
              <ol>
                {replay.recipe.steps.map((step, i) => (
                  <li
                    key={i}
                    aria-current={state.step === i ? 'step' : undefined}
                  >
                    <strong>{step.title}</strong> — {step.expected}
                  </li>
                ))}
              </ol>
              <h4>Pending held responses</h4>
              {!state.pending.length ? (
                <p>None</p>
              ) : (
                state.pending.map((p) => (
                  <p key={p.id}>
                    <code>{p.route}</code> · session {p.session}{' '}
                    <button onClick={() => replay?.release(p.id)}>
                      Release response {p.id}
                    </button>
                  </p>
                ))
              )}
              <h4>Harness diagnostics</h4>
              {state.diagnostics.length ? (
                state.diagnostics.map((m, i) => (
                  <p role="alert" key={i}>
                    {m}
                  </p>
                ))
              ) : (
                <p>No unmatched requests.</p>
              )}
              <details>
                <summary>Logical response sequence</summary>
                <ol>
                  {state.events.map((event, i) => (
                    <li key={i}>
                      <code>{event}</code>
                    </li>
                  ))}
                </ol>
              </details>
            </>
          )}
          <p>
            Route and per-route ordinal matching is test-harness machinery only.
            Extra harmless requests can shift ordinals; update recipes rather
            than constrain API behavior.
          </p>
        </>
      ) : (
        <>
          <h3>Contract Playground</h3>
          <label>Contract <select value={contractId} onChange={(e) => { const next = e.target.value === 'journal-preview' ? journalContract : acceptedContract; setContractId(next.id); setModel(Object.keys(next.parsers)[0]); setText(''); setResult(undefined); }}><option value="dashboard-api">Accepted API 0.1.2</option><option value="journal-preview">Journal preview 0.1.0 PROVISIONAL</option></select></label>
          <p>
            {contract.id === 'dashboard-api' ? 'Accepted API' : 'Journal preview'} {contract.version} ·{' '}
            {contract.disposition}. Shape acceptance is separate from
            semantic support and backend approval.
          </p>
          <details>
            <summary>Contract identity</summary>
            <code>{contract.sha256}</code>
          </details>
          <label>
            Response schema
            <select
              value={model}
              onChange={(e) => {
                setModel(e.target.value);
                setResult(undefined);
              }}
            >
              {Object.keys(contract.parsers).map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <button
            onClick={() => {
              if (contract.id === 'journal-preview') { setText(JSON.stringify(journalEnvelope(model === 'JournalResponse' ? story[4] : { items: story, next_cursor: null, components: ['parser'], kinds: [...new Set(story.map((r) => r.kind))] }), null, 2)); setResult(undefined); return; }
              const world = selectedWorld();
              const route = Object.entries(world.models).find(
                ([, name]) => name === model,
              )?.[0];
              const value = route
                ? world.responses[route]
                : worlds.flatMap((w) =>
                    Object.entries(w.models)
                      .filter(([, name]) => name === model)
                      .map(([path]) => w.responses[path]),
                  )[0];
              setText(JSON.stringify(value ?? {}, null, 2));
              setResult(undefined);
            }}
          >
            Load fixture
          </button>
          <label>
            Response JSON
            <textarea
              className="resize-none"
              rows={12}
              value={text}
              onChange={(e) => {
                const value = e.target.value;
                if (new TextEncoder().encode(value).length <= 256 * 1024) {
                  setText(value);
                  setResult(undefined);
                } else setMessage('Input exceeds 256 KiB');
              }}
            />
          </label>
          <button onClick={() => setResult(validateInput(model, text, contract))}>
            Validate
          </button>
          <button
            onClick={() => {
              setText('');
              setResult(undefined);
              setMessage('');
            }}
          >
            Clear input
          </button>
          <p>
            Input is memory-only, limited to 256 KiB, and never applied to
            dashboard projections. At most 100 issues are shown.
          </p>
          {result && (
            <div role="status">
              <strong>{result.status}</strong>
              <ul>
                {result.issues.map((issue, i) => (
                  <li key={i}>
                    <code>{issue.field}</code> · {issue.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      {message && (
        <p role="status" className="scope-note">
          {message}
        </p>
      )}
    </div>
  );
}
