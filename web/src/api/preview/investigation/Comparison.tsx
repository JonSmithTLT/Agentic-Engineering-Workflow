import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useReadSession, useProjection } from '../../../client/queries';
import { CopyDashboardLink } from '../../../components/CopyDashboardLink';
import { SourceStrip } from '../../../components/Investigation';
import { Pager, Reasons } from '../../../components/ProjectionViews';
import { ContextReferences as References } from './ContextReferences';
import { SafeContent } from '../../../components/Content';
import { SemanticValue } from '../../../components/States';
import { InvestigationTabs, focusBelowHeader } from '../../../components/InvestigationTabs';
import { useComparisonSource, useInvestigationReader } from './session';
import { investigationSchemas, investigationCases, type ComparisonSource } from './schema';
import { referenceIdentities, structuralState } from './model';
import { id as identity } from '../../schema';
import { invocationStatuses, invocationRoles, harnessStatuses } from '../../vocabulary';
const tabs = [{ id: 'overview', label: 'Overview' }, { id: 'configuration', label: 'Configuration' }, { id: 'references', label: 'References' }];
import { PacketInspector, packetTabs } from './PacketInspector';
import { useControls, ErrorState } from './ui';
function SourceChooser({ name, side }: { name: string; side: 'a' | 'b' }) {
  const { params, update } = useControls(), { reader, ready } = useInvestigationReader(`chooser:${side}`, name);
  const work = params.get('compare_work') ?? '', valid = !work || identity.safeParse(work).success;
  const route = '/sources?' + new URLSearchParams({ case: name, limit: '50', ...(work ? { work } : {}), ...(params.get('source_cursor') ? { cursor: params.get('source_cursor')! } : {}) });
  const query = useProjection(route, investigationSchemas.ComparisonSourceListResponse, 'history', ready && valid, true, reader);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { focusBelowHeader(heading.current); }, [side]);
  return <section className="panel source-chooser"><h2 tabIndex={-1} ref={heading}>Choose source {side.toUpperCase()}</h2>
    {side === 'a' && params.get('a_invocation') && <p>Starting invocation: <code>{params.get('a_invocation')}</code>. Select its explicit supplied source below; no snapshot is chosen automatically.</p>}
    <label>Work ID <input aria-label="Comparison work filter" value={work} onChange={event => update({ compare_work: event.target.value, source_cursor: null }, true)} /></label>
    {work && <button onClick={() => update({ compare_work: null, source_cursor: null })}>Clear work filter</button>}
    {!valid && <p role="alert">Malformed work ID; no collection request sent.</p>}
    <button onClick={() => update({ choose: null })}>Close source chooser</button>
    {query.error && <ErrorState error={query.error} retry={() => void query.refetch()} />}
    {query.data ? <><div className="table-scroll"><table role="table"><thead role="rowgroup"><tr role="row"><th>Source / supplied summary</th><th>Invocation</th><th>Work</th><th>Status</th><th>Snapshot / captured UTC</th></tr></thead><tbody role="rowgroup">{query.data.value.data.items.map(s => <tr role="row" key={s.id}><td role="cell"><button onClick={() => update({ [side + '_source']: s.id, [side + '_run']: null, choose: null })}>Select {s.id} for {side.toUpperCase()}</button><p className="source-choice-summary">{s.summary ?? 'No summary supplied.'}{s.summary_truncated && '… (supplied summary excerpt)'}</p></td><td role="cell"><span className="chooser-field-label">Invocation: </span><code>{s.invocation_id}</code></td><td role="cell"><span className="chooser-field-label">Work: </span><code>{s.work.id}</code></td><td role="cell"><span className="chooser-field-label">Status: </span><SemanticValue value={s.status} known={invocationStatuses} /></td><td role="cell"><span className="chooser-field-label">Snapshot / captured UTC: </span>{s.snapshot_id ?? 'Current source'}<br /><time>{s.captured_at ?? 'Capture time not supplied'}</time></td></tr>)}</tbody></table></div>
      {!query.data.value.data.items.length && <p className="empty">No comparison sources supplied for this filter.</p>}
      <Pager next={query.data.value.data.next_cursor} cursorKey="source_cursor" resetKey={`${name}:${work}`} /><details><summary>Collection response metadata</summary><SourceStrip source={query.data} failed={!!query.error} /></details></> : !query.error && <p role="status">Loading source choices…</p>}
  </section>;
}
type SourceQuery = ReturnType<typeof useComparisonSource>;
function SideHeader({ side, query, change }: { side: 'a' | 'b'; query: SourceQuery; change: () => void }) {
  const { params, update } = useControls(), source = query.data?.value.data, run = params.get(side + '_run') ?? '';
  return <section className="panel comparison-side" aria-label={`Source ${side.toUpperCase()}`}><h2>Source {side.toUpperCase()}</h2><button data-change-side={side} onClick={change}>Change {side.toUpperCase()}</button>
    {query.error && <ErrorState error={query.error} retry={() => void query.refetch()} />}
    {source ? <><p><code>{source.invocation.id}</code> · <code>{source.id}</code></p><p>{source.mode === 'FIXED' ? <>Snapshot <code>{source.snapshot_id}</code></> : 'Current source'} · <time>{source.captured_at ?? 'Capture time not supplied'}</time></p>
      <label>Harness run {side.toUpperCase()}<select value={run} onChange={event => update({ [side + '_run']: event.target.value })}><option value="">Invocation only — no run selected</option>{source.invocation.runs.map(r => <option key={r.id} value={r.id}>{r.id}</option>)}</select></label>
      {run && !source.invocation.runs.some(r => r.id === run) && <p role="alert">Selected harness run is not supplied for this invocation.</p>}
      <button onClick={() => void query.refetch()}>Refresh {side.toUpperCase()}</button>
      {query.error && <p role="status" className="preview-note">STALE / DISCONNECTED — displaying valid previous data.</p>}
      <details><summary>Source {side.toUpperCase()} response metadata</summary><SourceStrip source={query.data!} failed={!!query.error} readSnapshot={query.reader.context.identity.snapshot} /></details></> : !query.error && <p role="status">{params.get(side + '_source') ? 'Loading source…' : 'No source selected.'}</p>}
  </section>;
}
type Row = { label: string; left: unknown; right: unknown; complete?: boolean; render?: (value: unknown, side: 'a' | 'b') => ReactNode };
function ComparisonRows({ a, b, openPacket }: { a?: ComparisonSource; b?: ComparisonSource; openPacket: (side: 'a' | 'b', packet: string, target: HTMLElement) => void }) {
  const { params, update } = useControls(), active = params.get('compare_tab') ?? 'overview', differences = params.get('differences') === '1';
  const packetsFor = (source: ComparisonSource | undefined, side: 'a' | 'b') => source?.packets.filter(p => !params.get(side + '_run') || p.run_id === params.get(side + '_run') || p.run_id === null) ?? [];
  const runA = a?.invocation.runs.find(r => r.id === params.get('a_run')), runB = b?.invocation.runs.find(r => r.id === params.get('b_run'));
  let rows: Row[];
  if (active === 'overview') {
    rows = ['status', 'role', 'created_at'].map(field => ({ label: field.replaceAll('_', ' '), left: a?.invocation[field as 'status'], right: b?.invocation[field as 'status'], render: value => field === 'created_at' ? String(value ?? 'Not supplied') : <SemanticValue value={value as string ?? null} known={field === 'status' ? invocationStatuses : invocationRoles} /> }));
    rows.push({ label: 'Work', left: a?.invocation.work, right: b?.invocation.work, render: value => value ? <References values={[value as ComparisonSource['invocation']['work']]} /> : 'Not supplied' },
      { label: 'Summary (exact text)', left: a?.invocation.summary, right: b?.invocation.summary, render: value => value ? <SafeContent {...value as { format: string; text: string }} /> : 'Not supplied' },
      { label: 'Supplied reasons', left: a?.invocation.reasons, right: b?.invocation.reasons, render: value => value ? <Reasons values={value as ComparisonSource['invocation']['reasons']} /> : 'Not supplied' });
    for (const field of ['id', 'harness', 'kind', 'status', 'authority', 'launched_at'] as const) rows.push({ label: `Selected run ${field.replaceAll('_', ' ')}`, left: runA?.[field], right: runB?.[field], ...(field === 'status' || field === 'kind' ? { render: (value: unknown) => <SemanticValue value={value as string ?? null} known={field === 'status' ? harnessStatuses : ['launch', 'relaunch']} /> } : {}) });
  } else if (active === 'configuration') rows = ['work_revision', 'source_revision', 'environment', 'model_id', 'provider', 'profile_id', 'card_id', 'capability_id', 'prompt_id', 'prompt_version', 'prompt_digest'].map(field => ({ label: field.replaceAll('_', ' '), left: a?.[field as 'model_id'], right: b?.[field as 'model_id'] }));
  else rows = [
    { label: 'Evidence references', left: a && referenceIdentities(a.invocation.evidence), right: b && referenceIdentities(b.invocation.evidence), complete: !!a?.evidence_complete && !!b?.evidence_complete, render: (_, side) => { const source = side === 'a' ? a : b; return source ? <><References values={source.invocation.evidence} evidenceOrigin={{case: params.get("investigation_case") ?? "story", record_id:source.invocation.id,item_id:null,role:"invocation_evidence",source_id:source.id,snapshot_id:source.snapshot_id,visibility_scope:source.visibility_scope}} />{!source.evidence_complete && <p>Incomplete supplied evidence references.</p>}</> : 'Unavailable'; } },
    { label: 'Context packets', left: a && referenceIdentities(packetsFor(a, 'a').map(p => ({ kind: 'packet', id: p.id }))), right: b && referenceIdentities(packetsFor(b, 'b').map(p => ({ kind: 'packet', id: p.id }))), complete: !!a?.packets_complete && !!b?.packets_complete && (!params.get('a_run') || !!runA) && (!params.get('b_run') || !!runB), render: (_, side) => { const source = side === 'a' ? a : b; return source ? <><ul>{packetsFor(source, side).map(p => <li key={p.id}><button data-packet-link={`${side}:${p.id}`} onClick={event => openPacket(side, p.id, event.currentTarget)}>Inspect {p.id}</button> · {p.run_id ?? 'Invocation-level packet'}</li>)}</ul>{!packetsFor(source, side).length && <p>No context packet references supplied.</p>}{!source.packets_complete && <p>Incomplete supplied packet references.</p>}</> : 'Unavailable'; } },
  ];
  return <section aria-label="Structural comparison"><p className="scope-note">Structural comparison of supplied values. Differences do not establish causation. Array order does not indicate importance.</p>
    <InvestigationTabs prefix="compare" label="Comparison sections" tabs={tabs} active={active} select={id => update({ compare_tab: id })} />
    <label><input type="checkbox" checked={differences} onChange={event => update({ differences: event.target.checked ? '1' : null })} /> Show differences</label>
    <div role="tabpanel" id={`compare-panel-${active}`} aria-labelledby={`compare-tab-${active}`}>
      <div className="comparison-rows">{rows.filter(row => !differences || structuralState(row.left, row.right, row.complete) !== 'Same supplied value').map(row => <section className="comparison-row" key={row.label}><header><h3>{row.label}</h3><small>{structuralState(row.left, row.right, row.complete)}</small></header>{(['a', 'b'] as const).map(side => { const value = side === 'a' ? row.left : row.right; return <div className="comparison-value" key={side}><strong className="comparison-mobile-label">{side.toUpperCase()}</strong>{row.render ? row.render(value, side) : value === undefined || value === null ? <span className="muted">Not supplied / unavailable</span> : <span>{Array.isArray(value) ? value.join(' · ') : String(value)}</span>}</div>; })}</section>)}</div>
      {!rows.some(row => !differences || structuralState(row.left, row.right, row.complete) !== 'Same supplied value') && <p>No structural differences among the complete supplied values in this section.</p>}
    </div></section>;
}
function Workspace({ name }: { name: string }) {
  const { params, update } = useControls(), inspector = params.get('packet'), side = params.get('packet_side') === 'b' ? 'b' : 'a', choose = params.get('choose');
  const a = useComparisonSource('a', name, params.get('a_source') ?? '', !inspector, !!inspector && side === 'a'), b = useComparisonSource('b', name, params.get('b_source') ?? '', !inspector, !!inspector && side === 'b');
  const restore = useRef<{ key: string; scroll: number } | null>(null);
  const restoring = useRef(false);
  const previousChooser = useRef(choose);
  useEffect(() => {
    const prior = previousChooser.current;
    previousChooser.current = choose;
    if (!choose && (prior === 'a' || prior === 'b')) focusBelowHeader(document.querySelector(`[data-change-side="${prior}"]`));
  }, [choose]);
  const back = () => { restoring.current = true; update({ packet: null, packet_side: null, packet_cursor: null, packet_section: null, packet_disposition: null, packet_tab: null }); };
  useLayoutEffect(() => {
    if (inspector || !restoring.current) return;
    const target = Array.from(document.querySelectorAll<HTMLElement>('[data-packet-link]')).find(el => el.dataset.packetLink === restore.current?.key);
    if (restore.current && !target) return;
    window.scrollTo({ top: restore.current?.scroll ?? 0, behavior: 'instant' });
    focusBelowHeader(target ?? document.querySelector('.comparison-workspace h1'));
    restoring.current = false;
  }, [inspector, a.data, b.data]);
  return <div className="comparison-workspace"><h1 tabIndex={-1}>Invocation comparison</h1><p className="preview-note">Investigation preview · 0.1.0 PROVISIONAL · Fictional fixtures. Frontend acceptance is not backend adoption.</p>
    <p role="status">A: {params.get('a_source') ?? 'Not selected'} · B: {params.get('b_source') ?? 'Not selected'}</p><CopyDashboardLink />
    {inspector ? <PacketInspector query={side === 'a' ? a : b} packetId={inspector} name={name} back={back} /> : <>
      <div className="comparison-headings"><SideHeader side="a" query={a} change={() => update({ choose: 'a', source_cursor: null })} /><SideHeader side="b" query={b} change={() => update({ choose: 'b', source_cursor: null })} /></div>
      <button onClick={() => update({ a_source: params.get('b_source'), b_source: params.get('a_source'), a_run: params.get('b_run'), b_run: params.get('a_run') })}>Swap sides</button>
      {choose === 'a' || choose === 'b' ? <SourceChooser name={name} side={choose} /> : <ComparisonRows a={a.data?.value.data} b={b.data?.value.data} openPacket={(selectedSide, packet, target) => { restore.current = { key: target.dataset.packetLink ?? '', scroll: window.scrollY }; update({ packet, packet_side: selectedSide, packet_tab: 'contents', packet_cursor: null, packet_section: null, packet_disposition: null }); }} />}
    </>}
  </div>;
}
export default function Comparison() {
  const { params, update } = useControls(), base = useReadSession(), name = params.get('investigation_case') ?? 'story';
  const invalid = !investigationCases.includes(name as typeof investigationCases[number]) || ['a_source', 'b_source', 'a_run', 'b_run', 'packet'].some(k => params.has(k) && !identity.safeParse(params.get(k)).success) || (params.has('compare_tab') && !tabs.some(t => t.id === params.get('compare_tab'))) || (params.has('packet_tab') && !packetTabs.some(t => t.id === params.get('packet_tab'))) || ['rev', 'revision', 'snapshot'].some(k => params.has(k)) || (params.has('packet_side') && !['a', 'b'].includes(params.get('packet_side')!));
  return <><Link to="/runs">Back to Runs</Link><label className="filter-bar">Investigation scenario<select value={name} onChange={event => update({ investigation_case: event.target.value, source_cursor: null, packet_cursor: null, packet: null, packet_side: null })}>{investigationCases.map(c => <option key={c}>{c}</option>)}</select></label>
    {invalid ? <p role="alert">Unsupported or malformed comparison link. Historical links require an explicit supplied comparison source; no preview reads were sent.</p> : <Workspace key={`${base.generation}:${name}`} name={name} />}</>;
}
