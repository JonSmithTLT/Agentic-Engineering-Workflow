import { useRef, type ComponentType } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { InvestigationWorkspace } from '../../../components/InvestigationWorkspace';
import { RelationsExplorer } from '../../../components/RelationsExplorer';
import { SourceStrip } from '../../../components/Investigation';
import { SafeContent, JsonContent } from '../../../components/Content';
import { SemanticValue, LoadError } from '../../../components/States';
import { Pager } from '../../../components/ProjectionViews';
import { useProjection, projectionKey } from '../../../client/queries';
import { historicalRequested } from '../../navigation';
import { accessRefused } from '../../transport';
import { journalEntry, journalSchemas, journalKinds, applicabilityValues, journalCases, type JournalEntry, type JournalReference } from './schema';
import { journalContract } from './registration';
import { JournalSession, useJournalReader } from './session';
import { inspectJournal } from './model';
import { useQueryClient } from '@tanstack/react-query';
export default function JournalKnowledge({ Records }: {
    Records: ComponentType;
}) {
    const [params, setParams] = useSearchParams();
    const view = params.get('view') ?? 'journal', name = params.get('journal_case') ?? 'story';
    const invalid = !['journal', 'records'].includes(view) || !journalCases.includes(name as typeof journalCases[number]);
    return <>
    <div className="knowledge-mode" role="group" aria-label="Knowledge view">
      {['journal', 'records'].map((v) => <button key={v} aria-pressed={view === v} onClick={() => setParams((old) => {
                const p = new URLSearchParams(old);
                for (const k of ['selected', 'cursor', 'kind', 'component', 'component_missing', 'panel', 'display', 'inspector', 'field'])
                    p.delete(k);
                p.set('view', v);
                return p;
            })}>{v === 'journal' ? 'Journal' : 'Records'}</button>)}
    </div>
    {invalid ? <p role="alert">Unsupported journal presentation. No journal request was sent.</p> : view === 'records' ? <Records /> : <JournalSession name={name}><JournalWorkspace name={name}/></JournalSession>}
  </>;
}
function JournalWorkspace({ name }: {
    name: string;
}) {
    const [params, setParams] = useSearchParams(), results = useRef<HTMLDivElement>(null);
    const display = params.get('display') ?? 'stream', panel = params.get('panel') ?? 'summary';
    const error = historicalRequested(params) ? 'Historical snapshot reads are not supported by this preview.' :
        !['stream', 'table'].includes(display) || !['summary', 'evidence', 'provenance'].includes(panel) ||
            (params.has('selected') && !journalEntry.shape.id.safeParse(params.get('selected')).success) ||
            (params.has('component_missing') && params.get('component_missing') !== '1') ||
            (params.has('component') && params.has('component_missing')) ? 'Invalid journal presentation. No journal request was sent.' : null;
    if (error)
        return <p role="alert">{error}</p>;
    return <>
    <p className="preview-note" role="note">Journal preview · 0.1.0 PROVISIONAL · Fictional clangd investigation. Preview shape acceptance is not backend acceptance.</p>
    <label className="journal-case">Journal scenario <select aria-label="Journal scenario" value={name} onChange={(e) => setParams((old) => { const p = new URLSearchParams(old); p.set('journal_case', e.target.value); p.delete('cursor'); p.delete('selected'); return p; })}>
      {journalCases.map((c) => <option key={c}>{c}</option>)}
    </select></label>
    <InvestigationWorkspace collection="journal" title="Knowledge Journal" resultsLabel="Stream" selectionChanged={() => {
            // The shared close action commits URL state before this focus restoration.
            globalThis.requestAnimationFrame(() => {
                const target = [...(results.current?.querySelectorAll<HTMLAnchorElement>('[data-journal-id]') ?? [])].find((el) => el.dataset.journalId === params.get('selected'));
                (target ?? results.current)?.focus();
            });
        }} results={<div ref={results} tabIndex={-1}><JournalResults name={name} display={display}/></div>} detail={(id, shown) => <JournalDetail key={id} id={id} name={name} shown={shown} panel={panel}/>}/>
  </>;
}
function Reference({ reference }: {
    reference: JournalReference;
}) {
    const [params] = useSearchParams();
    if (reference.kind === 'journal') {
        const p = new URLSearchParams(params);
        p.set('selected', reference.id);
        p.set('panel', 'summary');
        return <Link to={'/knowledge?' + p}>{reference.id}{reference.title ? ` · ${reference.title}` : ''}</Link>;
    }
    return <span><code>{reference.id}</code>{reference.title ? ` · ${reference.title}` : ''} <small>({reference.kind}; supplied reference, no lookup interface)</small></span>;
}
function ReferenceList({ values, empty }: {
    values: JournalReference[];
    empty: string;
}) {
    return values.length ? <ul className="journal-references">{values.map((r, i) => <li key={i}><Reference reference={r}/></li>)}</ul> : <p className="muted">{empty}</p>;
}
function EntryLink({ entry }: {
    entry: JournalEntry;
}) {
    const [params] = useSearchParams(), p = new URLSearchParams(params);
    p.set('selected', entry.id);
    p.set('panel', 'summary');
    return <Link data-journal-id={entry.id} aria-current={params.get('selected') === entry.id ? 'true' : undefined} to={'/knowledge?' + p}>{entry.title}</Link>;
}
function JournalResults({ name, display }: {
    name: string;
    display: string;
}) {
    const reader = useJournalReader(), [params, setParams] = useSearchParams();
    const routeParams = new URLSearchParams({ case: name, limit: '50' });
    for (const k of ['component', 'component_missing', 'kind', 'cursor'])
        if (params.get(k))
            routeParams.set(k, params.get(k)!);
    const route = '/entries?' + routeParams;
    const query = useProjection(route, journalSchemas.JournalListResponse, 'history', true, true, reader);
    const data = query.data?.value.data;
    function change(key: string, value: string) {
        setParams((old) => {
            const p = new URLSearchParams(old);
            p.delete('cursor');
            if (key === 'component') {
                p.delete('component');
                p.delete('component_missing');
                if (value === 'missing')
                    p.set('component_missing', '1');
                else if (value)
                    p.set('component', value.slice(6));
            }
            else if (value)
                p.set(key, value);
            else
                p.delete(key);
            return p;
        });
    }
    return <section className="panel journal-results">
    <div className="filter-bar">
      <label>Component <select aria-label="Component" value={params.has('component_missing') ? 'missing' : params.has('component') ? 'value:' + params.get('component') : ''} onChange={(e) => change('component', e.target.value)}>
        <option value="">All components</option><option value="missing">Not supplied</option>
        {[...new Set([...(data?.components ?? []), ...(params.get('component') ? [params.get('component')!] : [])])].map((c) => <option key={c} value={'value:' + c}>{c}</option>)}
      </select></label>
      <label>Type <select aria-label="Type" value={params.get('kind') ?? ''} onChange={(e) => change('kind', e.target.value)}><option value="">All types</option>{[...new Set([...(data?.kinds ?? []), ...(params.get('kind') ? [params.get('kind')!] : [])])].map((k) => <option key={k}>{k}</option>)}</select></label>
      <label>Display <select aria-label="Display" value={display} onChange={(e) => setParams((old) => { const p = new URLSearchParams(old); p.set('display', e.target.value); return p; })}><option value="stream">Stream</option><option value="table">Table</option></select></label>
    </div>
    <p className="scope-note">Newest supplied publication first · UTC · 50 records per page. Retained does not mean current truth.</p>
    {!data ? query.isError ? <LoadError message={query.error.message} retry={() => void query.refetch()}/> : <p role="status">Loading journal…</p> : <>
      {query.isError && <p role="alert">Last known valid journal retained; refresh failed. <button onClick={() => void query.refetch()}>Retry journal</button></p>}
      {params.get('selected') && !data.items.some((r) => r.id === params.get('selected')) && <p className="preview-note">Selected entry is outside these results. Its detail remains selected.</p>}
      {!data.items.length && <p className="empty">No journal entries in these results. Change the filters or scenario.</p>}
      {display === 'table' ? <div className="table-scroll"><table><thead><tr><th>Entry</th><th>Type</th><th>Published (UTC)</th><th>Applicability</th><th>Component</th></tr></thead><tbody>{data.items.map((r) => <tr key={r.id}><td><code>{r.id}</code><br /><EntryLink entry={r}/></td><td><SemanticValue value={r.kind} known={journalKinds}/></td><td>{r.published_at ?? 'Undated'}</td><td><SemanticValue value={r.applicability} known={applicabilityValues}/></td><td>{r.component ?? 'Not supplied'}</td></tr>)}</tbody></table></div> : <ol className="journal-stream">{data.items.map((r, i) => {
                    const date = r.published_at?.slice(0, 10) ?? 'Undated', previous = data.items[i - 1]?.published_at?.slice(0, 10) ?? 'Undated';
                    return <li key={r.id} className="journal-item" data-kind={journalKinds.includes(r.kind) ? r.kind : 'unknown'}>
          {(i === 0 || date !== previous) && <h2 className="journal-date">{date}</h2>}
          <div className="journal-type"><SemanticValue value={r.kind} known={journalKinds}/><time dateTime={r.published_at ?? undefined}>{r.published_at ? r.published_at.slice(11, 19) + ' UTC' : 'Publication not supplied'}</time></div>
          <h3><EntryLink entry={r}/></h3>
          <p><code>{r.id}</code> · <SemanticValue value={r.applicability} known={applicabilityValues}/> · {r.origin.work?.id ?? 'Origin not supplied'}</p>
        </li>;
                })}</ol>}
      <Pager next={data.next_cursor} resetKey={JSON.stringify([name, params.get('component'), params.get('component_missing'), params.get('kind')])}><span>{data.items.length} supplied on this page</span></Pager>
    </>}
  </section>;
}
function JournalDetail({ id, name, shown, panel }: {
    id: string;
    name: string;
    shown: boolean;
    panel: string;
}) {
    const reader = useJournalReader(), client = useQueryClient(), [, setParams] = useSearchParams();
    const route = `/entries/${encodeURIComponent(id)}?case=${encodeURIComponent(name)}`;
    const query = useProjection(route, journalSchemas.JournalResponse, 'detail', true, shown, reader);
    const result = query.data, r = result?.value.data;
    if (!r || !result)
        return query.isError ? <LoadError message={query.error.message} retry={() => void query.refetch()}/> : <p role="status">Loading selected entry…</p>;
    const inspection = inspectJournal(r, result);
    return <article className="panel journal-detail">
    {query.isError && <p role="alert">Last known valid entry retained; refresh failed. <button onClick={() => void query.refetch()}>Retry entry</button></p>}
    <p className="journal-type"><code>{r.id}</code> · <SemanticValue value={r.kind} known={journalKinds}/></p>
    <h2>{r.title}</h2>
    <p>Applicability: <SemanticValue value={r.applicability} known={applicabilityValues}/></p>
    <div className="journal-tabs" role="tablist" aria-label="Entry detail">
      {['summary', 'evidence', 'provenance'].map((tab, index) => <button key={tab} id={`journal-tab-${tab}`} role="tab" aria-selected={panel === tab} aria-controls={`journal-panel-${tab}`} tabIndex={panel === tab ? 0 : -1} onClick={() => setParams((old) => { const p = new URLSearchParams(old); p.set('panel', tab); return p; })} onKeyDown={(e) => {
                const tabs = ['summary', 'evidence', 'provenance'];
                const next = e.key === 'ArrowRight' ? (index + 1) % 3 : e.key === 'ArrowLeft' ? (index + 2) % 3 : e.key === 'Home' ? 0 : e.key === 'End' ? 2 : -1;
                if (next >= 0) {
                    e.preventDefault();
                    document.getElementById(`journal-tab-${tabs[next]}`)?.click();
                    document.getElementById(`journal-tab-${tabs[next]}`)?.focus();
                }
            }}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}
    </div>
    <section id="journal-panel-summary" role="tabpanel" aria-labelledby="journal-tab-summary" hidden={panel !== 'summary'}>
      <h3>Claim</h3><SafeContent {...r.claim}/>
      <h3>Why retained</h3>
      {r.retention_explanation.state === 'SUPPLIED' && r.retention_explanation.text ? <p>{r.retention_explanation.text}</p> : <p>No retention explanation supplied.</p>}
      {!['SUPPLIED', 'MISSING', 'DENIED', 'UNKNOWN'].includes(r.retention_explanation.state) && <p>Unknown explanation state: {r.retention_explanation.state}</p>}
      {r.retention_explanation.state === 'DENIED' && <p>Retention explanation access unavailable.</p>}
      <h3>Conditions</h3><TextList values={r.conditions} empty="No applicability conditions supplied."/>
      <h3>Limitations</h3><TextList values={r.limitations} empty="No limitations supplied."/>
    </section>
    <section id="journal-panel-evidence" role="tabpanel" aria-labelledby="journal-tab-evidence" hidden={panel !== 'evidence'}>
      <h3>Supporting evidence</h3><ReferenceList values={r.supporting_evidence} empty="No supporting evidence references supplied."/>
      <h3>Opposing evidence</h3><ReferenceList values={r.opposing_evidence} empty="No opposing evidence references supplied."/>
      <p className="scope-note">These roles are supplied. References do not independently establish acceptance or applicability.</p>
    </section>
    <section id="journal-panel-provenance" role="tabpanel" aria-labelledby="journal-tab-provenance" hidden={panel !== 'provenance'}>
      <h3>Exact origin</h3><dl><dt>Work</dt><dd>{r.origin.work ? <Reference reference={r.origin.work}/> : 'Not supplied'}</dd><dt>Attempt</dt><dd>{r.origin.attempt_id ?? 'Not supplied'}</dd><dt>Invocation</dt><dd>{r.origin.invocation ? <Reference reference={r.origin.invocation}/> : 'Not supplied'}</dd><dt>Run</dt><dd>{r.origin.run_id ?? 'Not supplied'}</dd><dt>Source revision</dt><dd><code>{r.origin.source_revision ?? 'Not supplied'}</code></dd><dt>Environment</dt><dd>{r.origin.environment.join(' · ') || 'Not supplied'}</dd><dt>Published (UTC)</dt><dd>{r.published_at ?? 'Not supplied'}</dd><dt>Observed (UTC)</dt><dd>{r.observed_at ?? 'Not supplied'}</dd><dt>Derived (UTC)</dt><dd>{r.derived_at ?? 'Not supplied'}</dd></dl>
      <details><summary>Producer and prompt identity metadata</summary><dl>{['producer', 'model_id', 'prompt_id', 'prompt_version', 'prompt_digest'].map((k) => <div key={k}><dt>{k}</dt><dd>{k === 'producer' ? r.producer ? `${r.producer.id} · ${r.producer.role ?? 'Role not supplied'}` : 'Not supplied' : String(r[k as 'model_id'] ?? 'Not supplied')}</dd></div>)}</dl><p>Identity metadata only. Raw prompt content is not part of this preview.</p></details>
      <h3>Canonical references</h3><ReferenceList values={r.canonical_references} empty="No canonical references supplied."/>
      <p className="scope-note">Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.</p>
      <h3>Origin relations</h3>
      <p className="scope-note">The graph contains only loaded supplied relations within the displayed bounds. Absence of a relationship is not evidence that no relationship exists.</p>
      <ReferenceList values={r.relations.map((rel) => ({ ...rel.target, title: `${rel.relation}${rel.target.title ? ' · ' + rel.target.title : ''}` }))} empty="No origin relations supplied."/>
      <details><summary>Explore bounded origin graph</summary>
        <RelationsExplorer key={`${id}:${reader.context.generation}`} root={inspection} reader={{ context: reader.context, canLoad: (kind) => kind === 'journal', anchor: (entity) => <Reference reference={{ ...entity, title: entity.title ?? null }}/>, load: async (_kind, target, signal) => {
                const path = `/entries/${encodeURIComponent(target)}?case=${encodeURIComponent(name)}`;
                try {
                    const loaded = await client.fetchQuery({ queryKey: projectionKey(path, reader), queryFn: () => reader.get(path, journalSchemas.JournalResponse, signal) });
                    return inspectJournal(loaded.value.data, loaded);
                }
                catch (error) {
                    if (accessRefused(error))
                        client.removeQueries({ queryKey: projectionKey(path, reader), exact: true });
                    throw error;
                }
            } }}/>
      </details>
      <details><summary>Response provenance and browser check</summary><SourceStrip source={result} failed={query.isError}/><p>Preview contract digest: <code>{journalContract.sha256}</code></p><JsonContent value={{ id: r.id, contract: journalContract.artifact }}/></details>
    </section>
  </article>;
}
function TextList({ values, empty }: {
    values: string[];
    empty: string;
}) {
    return values.length ? <ul>{values.map((v, i) => <li key={i}>{v}</li>)}</ul> : <p className="muted">{empty}</p>;
}
