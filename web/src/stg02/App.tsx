import { useEffect, useRef, useState } from 'react';
import { array, exchange, object, PACKAGE_DIGEST, prepareContinue, readPath, text, validateReceiptBinding, WireProblem } from './wire';
import type { Json, ObjectValue, ReadKind } from './wire';
import fixtureRequest from './contracts/fixture-continue-request.json';

const kinds: ReadKind[] = ['waiting', 'run', 'continuation', 'operations', 'operation'];
const recoveryKey = `aew-stg02-recovery:${PACKAGE_DIGEST}`;
function Facts({ value }: { value: ObjectValue }) {
  return <dl className="stg02-facts">{Object.entries(value).map(([name, item]) => <div key={name}><dt>{name.replaceAll('_', ' ')}</dt><dd>{item !== null && typeof item === 'object' ? <details><summary>Inspect {name.replaceAll('_', ' ')}</summary>{Array.isArray(item) ? <ol>{item.map((part, i) => <li key={i}>{part !== null && typeof part === 'object' ? <Facts value={object(part)} /> : text(part)}</li>)}</ol> : <Facts value={item} />}</details> : text(item)}</dd></div>)}</dl>;
}
function Source({ item }: { item: ObjectValue }) {
  const stamp = object(item.source);
  return <><p className="banner">Supplied source stamp: {text(stamp.owner)} · {text(stamp.observation_state)} · {text(stamp.qualification)}<br />Last-known observation: {text(stamp.observed_at)} · Basis: {text(stamp.fact_ref)}<br />Source validity bound: {text(object(stamp.renewal).valid_until)}. This recording does not establish current validity.</p><details><summary>Source and field attribution</summary><Facts value={{ source: item.source ?? null, field_sources: item.field_sources ?? null }} /></details></>;
}
function locationFor(kind: ReadKind, id = '', cursor = '') {
  const params = new URLSearchParams({ view: kind });
  if (id) params.set('id', id);
  if (cursor) params.set('cursor', cursor);
  return `/stg02?${params}`;
}
function closure(data: ObjectValue) {
  const page = object(data.page);
  if (page.has_more === true) return 'More pages follow. This page is not the complete list.';
  if (page.membership === 'qualified_scoped') return array(data.items).length ? 'Complete for the requested recipient scope.' : 'None in the requested recipient scope. This is not global absence.';
  return 'Incomplete membership: absence here does not establish that no other items exist.';
}
function Resource({ value }: { value: Json }) {
  const item = object(value), data = object(item.data), ref = object(item.ref);
  const effectSource = object(array(item.field_sources).map(object).find(field => field.field_path === 'data.remote_effect_state')?.source);
  return <article className="panel"><h2>{text(ref.id)} · {text(item.resource_type)}</h2><Source item={item} />
    {array(item.links).filter(link => object(link).availability === 'navigable' && object(object(link).target).kind === 'execution_activity').map((link, index) => <p key={index}><a href={locationFor('run', text(object(object(link).target).id))}>Inspect supplied execution {text(object(object(link).target).id)}</a></p>)}
    {item.resource_type === 'waiting' && <><Facts value={{ work: data.work ?? null, cause: data.cause ?? null, responsible_owner: data.responsible_owner ?? null, progress: data.progress ?? null, narrative: data.narrative ?? null, action_status: data.action_status ?? null }} /><a href={locationFor('continuation', text(object(data.work).id))}>Inspect continuation information for {text(object(data.work).id)}</a><p>A waiting notice is not an owner action. No run association is inferred.</p></>}
    {item.resource_type === 'run' && <><h3>Recorded progress</h3><Facts value={{ phase: data.phase ?? null, phase_observation_class: data.phase_observation_class ?? null, phase_basis_ref: data.phase_basis_ref ?? null, last_progress_at: data.last_progress_at ?? null }} /><h3>Remote effect</h3><Facts value={{ remote_effect_state: data.remote_effect_state ?? null, remote_effect_domain: data.remote_effect_domain ?? null, remote_effect_basis_ref: data.remote_effect_basis_ref ?? null, effect_source_owner: effectSource.owner ?? null, effect_source_basis: effectSource.fact_ref ?? null, effect_observed_at: effectSource.observed_at ?? null, effect_source_qualification: effectSource.qualification ?? null, effect_observation_state: effectSource.observation_state ?? null }} /><p>Unknown is neither done nor failed. Model-delivery observations do not establish whole-invocation clearance.</p>{typeof object(data.work_ref).id === 'string' && <a href={locationFor('continuation', text(object(data.work_ref).id))}>Inspect continuation information for supplied work {text(object(data.work_ref).id)}</a>}</>}
    {item.resource_type === 'continuation_vector' && <><p className="banner">Information only — never permission to act. HEB independently decides command admission.</p><div className="stg02-axes">{Object.entries(object(data.axes)).map(([owner, axis]) => { const row = object(axis); return <section className="panel" key={owner}><h3>{owner}: {text(row.state)}</h3><Facts value={{ qualification: row.qualification ?? null, reason_code: row.reason_code ?? null, basis_ref: row.basis_ref ?? null, observed_at: row.observed_at ?? null }} /><details><summary>{owner} epoch and validity</summary><Facts value={row} /></details></section>; })}</div></>}
    {item.resource_type === 'owner_operation_index' && <><Facts value={data} /><a href={locationFor('operation', `${text(data.owner)}|${text(data.operation_ref)}`)}>Read owner observation: {text(data.owner)} / {text(data.operation_ref)}</a></>}
    <details><summary>Complete supplied record</summary><Facts value={item} /></details>
  </article>;
}

export function ContinueControl() {
  const [input, setInput] = useState('');
  const [prepared, setPrepared] = useState<string>();
  const [recovery, setRecovery] = useState<string>();
  const [chosen, setChosen] = useState<string[]>([]);
  const [receipt, setReceipt] = useState<ObjectValue>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const active = useRef(true);
  const inFlight = useRef(false);
  useEffect(() => {
    active.current = true;
    try {
      const stored = sessionStorage.getItem(recoveryKey);
      if (stored) setRecovery(prepareContinue(JSON.parse(stored)));
    } catch { setError('Recovery storage is unavailable or invalid. No command was sent.'); }
    return () => { active.current = false; };
  }, []);
  async function submit(body: string) {
    if (inFlight.current || conflict) return;
    inFlight.current = true;
    setError(''); setReceipt(undefined); setBusy(true);
    try {
      // Persist BEFORE dispatch; failure must not create an unrecoverable send.
      sessionStorage.setItem(recoveryKey, body);
      setRecovery(body);
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 15000);
      try {
        const result = validateReceiptBinding(await exchange('receipt', '/o01/v0/command-sets', controller.signal, fetch, body), body);
        if (active.current) setReceipt(result);
      } finally { window.clearTimeout(timeout); }
    } catch (failure) {
      if (!active.current) return;
      if (failure instanceof WireProblem && failure.body.code === 'request_key_conflict') setConflict(true);
      setError(failure instanceof Error ? failure.message : 'No validated receipt; outcome unknown.');
    } finally { inFlight.current = false; if (active.current) setBusy(false); }
  }
  const intents = prepared ? array(object(JSON.parse(prepared)).intents) : [];
  return <section className="panel"><h2>Deliberately select work to continue</h2><p>This submits a separate CURRENT_DELEGATED_GRANT command to HEB. Continuation information does not enable or authorize it. Synthetic testing uses a labelled fixture delegation only.</p>
    <button type="button" disabled={busy || !!recovery} onClick={() => { setInput(JSON.stringify(fixtureRequest)); setPrepared(prepareContinue(fixtureRequest)); setChosen([]); setError(''); }}>Review work supplied by the fixture delegation</button>
    <details><summary>Inspect or supply the separate request</summary><label htmlFor="stg02-request">Independently supplied command set (JSON; no credentials)</label><textarea id="stg02-request" rows={8} value={input} onChange={e => { setInput(e.target.value); setPrepared(undefined); setChosen([]); }} disabled={busy || !!recovery} />
    <button type="button" disabled={busy || !!recovery} onClick={() => { try { setPrepared(prepareContinue(JSON.parse(input))); setChosen([]); setError(''); } catch (failure) { setPrepared(undefined); setError(failure instanceof Error ? failure.message : 'Invalid request'); } }}>Review separate request</button></details>
    {prepared && <fieldset><legend>Select every supplied intent deliberately</legend>{intents.map(intent => { const row = object(intent), target = object(row.target), id = text(row.intent_ref); return <label key={id}><input type="checkbox" checked={chosen.includes(id)} disabled={busy || !!recovery} onChange={e => setChosen(current => e.target.checked ? [...current, id] : current.filter(x => x !== id))} />{id} · Work {text(target.work_ref)} at {text(target.work_revision)} · Delegation {text(row.delegated_grant_proof_ref)}</label>; })}<button disabled={busy || !!recovery || chosen.length !== intents.length} type="button" onClick={() => void submit(prepared)}>Submit selected work to HEB</button></fieldset>}
    {busy && <p role="status">Waiting for a receipt. An effect is not established.</p>}
    {error && <p role="alert">{error} No validated receipt from this attempt; the owner outcome is not established here.</p>}
    {receipt && <section><h3>202 — received, not done</h3><p>Each result is shown in request order. Only an owner's qualified observation establishes an effect.</p><Facts value={{ carrier_state: receipt.carrier_state ?? null, request_set_ref: receipt.request_set_ref ?? null, observed_at: receipt.observed_at ?? null, source_valid_until: receipt.source_valid_until ?? null }} /><ol>{array(receipt.results).map((result, i) => { const row = object(result); return <li key={i}><h4>{text(row.intent_ref)} · {text(row.owner)}</h4><Facts value={row} />{typeof row.operation_ref === 'string' && typeof row.owner === 'string' ? <p><a href={locationFor('operation', `${row.owner}|${row.operation_ref}`)}>Inspect exact owner outcome: {row.owner} / {row.operation_ref}</a></p> : <p>No owner-operation identity supplied for {text(row.intent_ref)}. Outcome remains unestablished.</p>}</li>; })}</ol></section>}
    {recovery && <><details><summary>Original request identity for recovery</summary><Facts value={object(JSON.parse(recovery))} /></details><p>After reload, read the owner-operation index and owner observation. Missing observations leave the outcome unknown.</p><a href={locationFor('operations')}>Inspect owner-operation outcomes</a><button type="button" disabled={busy || conflict} onClick={() => void submit(recovery)}>Reconcile using the same key and exact body</button><p>A retry is a lookup. No automatic retry or new key is generated. A key conflict stops reconciliation.</p></>}
  </section>;
}

export default function App() {
  const url = new URL(window.location.href);
  const rawKind = url.searchParams.get('view') ?? 'waiting';
  const kind = kinds.includes(rawKind as ReadKind) ? rawKind as ReadKind : undefined;
  const id = url.searchParams.get('id') ?? '', cursor = url.searchParams.get('cursor') ?? '';
  const invalid = [...url.searchParams.keys()].some(key => !['view', 'id', 'cursor'].includes(key) || url.searchParams.getAll(key).length !== 1) || !kind;
  const [data, setData] = useState<ObjectValue>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (invalid || !kind) return;
    const controller = new AbortController(); let retired = false;
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    setLoading(true); setData(undefined); setError('');
    let path: string;
    try { path = readPath(kind, id, cursor); } catch (failure) { setLoading(false); setError(String(failure)); window.clearTimeout(timeout); return; }
    void exchange(kind, path, controller.signal).then(result => {
      if (retired) return;
      const item = object(array(result.items)[0]);
      if ((kind === 'run' && object(item.ref).id !== id) || (kind === 'continuation' && object(item.data).work_ref !== id) || (kind === 'operation' && `${text(result.owner)}|${text(result.operation_ref)}` !== id)) throw new Error('Rejected route/resource binding');
      setData(result);
    }).catch(failure => { if (!retired) { setData(undefined); setError(failure instanceof Error ? failure.message : 'No validated representation'); } }).finally(() => { window.clearTimeout(timeout); if (!retired) setLoading(false); });
    return () => { retired = true; controller.abort(); window.clearTimeout(timeout); };
  }, [kind, id, cursor, invalid, revision]);
  return <main className="stg02"><header><h1>Waiting work & continuation</h1><p>STG-02 · adopted D-01 0.3.4 / O-01 0.2 · separate contract path</p><p className="banner">Fixture investigation — unqualified preview. Recorded or explicitly derived synthetic facts; no live owner authority or protected operation is established here.</p><details><summary>Selected contract identity</summary><code>sha256:{PACKAGE_DIGEST}</code></details></header>
    <nav aria-label="STG-02 views"><a href={locationFor('waiting')}>Waiting work</a><a href={locationFor('operations')}>Owner operations</a></nav>
    <form method="get" action="/stg02"><label>Read view<select name="view" defaultValue={kind ?? 'waiting'}><option value="waiting">Waiting work</option><option value="run">Run detail</option><option value="continuation">Continuation information</option><option value="operations">Owner-operation index</option><option value="operation">Owner observation</option></select></label><label>Exact supplied ID (owner|operation for owner observation)<input name="id" defaultValue={id} /></label><button type="submit">Open exact read</button></form>
    {invalid ? <p role="alert">Unsupported or duplicate link parameters. No slice read made.</p> : <><button type="button" disabled={loading} onClick={() => setRevision(x => x + 1)}>Refresh this read</button>{loading && <p role="status">Loading a source-qualified read…</p>}{error && <p role="alert">{error}. No current representation is established.</p>}</>}
    {data && <><section className="panel"><h2>Read outcome: {text(data.outcome ?? object(data.result).effect_state)}</h2><Facts value={kind === 'operation' ? data : { continuity: data.continuity ?? null, projection_as_of: data.projection_as_of ?? null, correlation_id: data.correlation_id ?? null }} />{data.limitations !== undefined && <p><strong>Limitations:</strong> {array(data.limitations).length ? array(data.limitations).map(text).join(' · ') : 'None supplied'}</p>}<p>Source observation time and validity belong to the supplied facts. Fetch time does not renew them.</p>{data.page !== null && data.page !== undefined && <><p>{closure(data)}</p>{object(data.page).has_more === true && typeof object(data.page).next_cursor === 'string' && <a href={locationFor(kind!, id, text(object(data.page).next_cursor))}>Next supplied page</a>}</>}</section>{array(data.items).map((item, index) => <Resource key={index} value={item} />)}</>}
    <section className="panel"><h2>Protected actions — held</h2><p>Close attachment, reattach Lead, attach Lead and other PROTECTED_G3 actions are held: G3_unqualified. No protected command control or simulated operation is offered.</p></section>
    <ContinueControl />
  </main>;
}
