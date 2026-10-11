import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { MapsResponse, StructuralListResponse, StructuralDetailResponse, StructuralInputsResponse, MapDiffResponse, Sha256, ObjectId } from '../api/additive-schema';
import { mapsRoute, storedMapsRoute, structuralMapRoute, mapInputsRoute, mapDiffRoute } from '../api/maps-history';
import { mapPresentation, mapSections } from '../api/maps-presentation';
import { useMapRead } from '../client/maps';
import { CapabilityGate, useCapability } from '../client/dashboard';
import { CopyDashboardLink } from '../components/CopyDashboardLink';
import { EntityAnchor } from '../components/EntityAnchor';
import { SourceStrip } from '../components/Investigation';
import { InvestigationTabs, focusBelowHeader } from '../components/InvestigationTabs';
import { Pager, Reasons } from '../components/ProjectionViews';
import { SemanticValue } from '../components/States';
import type { Projection } from '../api/transport';
import { rememberReference, restoreReference, returnPosition } from '../components/reference-return';
const title = (value: string) => value.charAt(0).toUpperCase() + value.slice(1).replaceAll('_', ' ');
type Envelope = { schema_version: string; project_id: string; control_revision: string; generated_at: string };

/** Escaped supplied data only. No artifact paths become links or commands. */
function Fields({ value, semantic = {} }: { value: unknown; semantic?: Record<string, readonly string[]> }) {
  if (value === null || value === undefined) return <span>Not supplied</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <p>No entries supplied in this projection.</p>;
    if (value.every(item => typeof item === 'object' && item !== null && !Array.isArray(item))) {
      const columns = [...new Set(value.flatMap(item => Object.keys(item)))];
      return <div className="table-scroll"><table><thead><tr>{columns.map(key => <th key={key}>{title(key)}</th>)}</tr></thead><tbody>{value.map((item, index) => <tr key={index}>{columns.map(key => <td key={key} data-label={title(key)}><Fields value={item[key]} /></td>)}</tr>)}</tbody></table></div>;
    }
    return <ul>{value.map((item, index) => <li key={index}><Fields value={item} /></li>)}</ul>;
  }
  if (typeof value === 'object') return <dl>{Object.entries(value).map(([key, item]) => <div key={key}><dt>{title(key)}</dt><dd>{semantic[key] && typeof item === 'string' ? <SemanticValue value={item} known={semantic[key]} /> : <Fields value={item} />}</dd></div>)}</dl>;
  return <span className="map-value">{String(value)}</span>;
}
function ReadState({ query, children }: { query: { data?: Projection<Envelope>; isPending: boolean; isFetching: boolean; error: Error | null; refetch: () => unknown }; children: ReactNode }) {
  return <>
    {query.error && <p role="alert" className="preview-note">{query.data ? 'Refresh failed. Displaying last-known-good data. ' : 'Projection unavailable. '}{query.error.message}</p>}
    {query.isPending && !query.data && !query.error && <p role="status">Loading Maps projection…</p>}
    <button className="map-refresh" disabled={query.isFetching} onClick={() => { void query.refetch(); }}>{query.isFetching ? 'Reading…' : 'Refresh this projection'}</button>
    {query.data && <>{children}<details><summary>Source and browser metadata</summary><SourceStrip source={query.data} failed={!!query.error} /></details></>}
  </>;
}
function Overview({ against }: { against?: string }) {
  const location = useLocation();
  const restored = useRef<string | null>(null);
  const [params, setParams] = useSearchParams();
  const schema = MapsResponse.refine(value => !against || !value.data.structural.freshness?.against_commit || value.data.structural.freshness.against_commit === against, 'Compared-against commit binding mismatch');
  const query = useMapRead(mapsRoute({ against }), schema, useCapability('maps').available, true);
  const data = query.data?.value.data;
  useEffect(() => {
    const position = returnPosition(location.state);
    const link = document.querySelector<HTMLAnchorElement>('[data-map-architecture] a');
    if (data && position?.reference === 'map-architecture' && link && restored.current !== location.key) { restoreReference(position, link); restored.current = location.key; }
  }, [data, location.state, location.key]);
  useEffect(() => {
    if (data?.structural.summary && !params.has('map_root')) setParams(old => { const p = new URLSearchParams(old); p.set('map_root', data.structural.summary!.root); return p; }, { replace: true });
  }, [data, params, setParams]);
  return <ReadState query={query}>{data && <>
    <p>{data.label}</p><div className="map-summary-facts"><p>Registry: <SemanticValue value={data.registry.state} known={['PRESENT', 'NONE', 'INVALID']} /></p><p>Map revision: <code>{data.map_revision ?? 'Not supplied'}</code></p><p>Stored maps: {data.stored.count}</p><p>Selected artifact: <SemanticValue value={data.structural.state} known={['AVAILABLE', 'UNAVAILABLE']} /></p></div>
    {!!data.registry.reasons.length && <Reasons values={data.registry.reasons} />}{!!data.structural.reasons.length && <Reasons values={data.structural.reasons} />}
    {data.structural.summary && <p>Registry-selected root: <code>{data.structural.summary.root}</code> · Source commit: <code>{data.structural.summary.source_revision ?? 'Not supplied'}</code></p>}
    {data.structural.freshness && <><p>Registry-selected freshness: <SemanticValue value={data.structural.freshness.status} known={['CURRENT', 'STALE', 'UNKNOWN']} /> · Compared against <code>{data.structural.freshness.against_commit ?? 'Not supplied'}</code></p><Reasons values={data.structural.freshness.reasons} /></>}
    {data.architecture && <section className="map-architecture"><h2>Architecture reference</h2>{data.architecture.evidence && <span data-map-architecture onClickCapture={event => { if ((event.target as Element).closest('a')) rememberReference('map-architecture'); }}><EntityAnchor entity={data.architecture.evidence} /></span>}<SemanticValue value={data.architecture.freshness.status} known={['CURRENT', 'STALE', 'UNKNOWN', 'UNAVAILABLE']} /><p>{data.architecture.note}</p><details><summary>Architecture source and freshness</summary><Fields value={data.architecture.freshness} semantic={{ status: ['CURRENT', 'STALE', 'UNKNOWN', 'UNAVAILABLE'] }} /></details></section>}
    <SelectedRoot root={data.structural.summary?.root ?? null} against={against} />
  </>}</ReadState>;
}
function Stored() {
  const location = useLocation();
  const restored = useRef<string | null>(null);
  const [params, setParams] = useSearchParams();
  const [source, setSource] = useState(params.get('map_source_revision') ?? '');
  const [error, setError] = useState('');
  const suppliedSource = params.get('map_source_revision') ?? '';
  useEffect(() => { setSource(suppliedSource); setError(''); }, [suppliedSource]);
  const route = storedMapsRoute({ limit: 50, cursor: params.get('map_cursor') ?? undefined, source_revision: params.get('map_source_revision') ?? undefined });
  const query = useMapRead(route, StructuralListResponse, useCapability('maps').available);
  const data = query.data?.value.data;
  useEffect(() => {
    const position = returnPosition(location.state);
    if (!position || !data || restored.current === location.key) return;
    const control = [...document.querySelectorAll<HTMLElement>('[data-map-root]')].find(element => element.dataset.mapRoot === position.reference);
    if (control) { restoreReference(position, control); restored.current = location.key; }
  }, [data, location.state, location.key]);
  return <ReadState query={query}>{data && <>
    <p>{data.label}</p><form noValidate onSubmit={event => { event.preventDefault(); if (source && !ObjectId.safeParse(source).success) { setError('Enter a complete source commit identity.'); focusBelowHeader(event.currentTarget.querySelector('input')); return; } setError(''); setParams(old => { const p = new URLSearchParams(old); if (source) p.set('map_source_revision', source); else p.delete('map_source_revision'); p.delete('map_cursor'); return p; }); }}><label>Stored source commit <input value={source} aria-invalid={!!error} aria-describedby={error ? 'map-source-error' : undefined} onChange={event => setSource(event.target.value)} /></label><button>Filter stored maps</button>{error && <p id="map-source-error" role="alert">{error}</p>}</form>
    {params.get('map_root') && <p role="status">Viewed map: <code>{params.get('map_root')}</code>{!data.items.some(item => item.root === params.get('map_root')) && ' · Not on this loaded page; this does not establish unavailability.'}</p>}
    {(params.get('map_a') || params.get('map_b')) && <p>Chosen comparison A: <code>{params.get('map_a') ?? 'Not selected'}</code> · B: <code>{params.get('map_b') ?? 'Not selected'}</code></p>}
    {data.scan_incomplete && <div className="preview-note"><strong>Stored-map scan incomplete</strong><Fields value={data.scan_incomplete} /></div>}
    <div className="table-scroll"><table><caption>Stored maps · 50 entries per page</caption><thead><tr><th>Root</th><th>Source revision</th><th>Status</th><th>Selected</th><th>Comparison</th></tr></thead><tbody>{data.items.map(item => <tr key={item.root}><td><button data-map-root={item.root} onClick={() => { rememberReference(item.root); setParams(old => { const p = new URLSearchParams(old); p.set('map_root', item.root); p.set('map_activity', 'selected'); p.delete('map_input_cursor'); return p; }); }}><code>{item.root}</code></button></td><td><code>{item.source_revision ?? 'Not supplied'}</code></td><td><SemanticValue value={item.status} known={['AVAILABLE', 'CORRUPT']} /><Reasons values={item.reasons} /></td><td>{item.selected ? 'Yes' : 'No'}</td><td>{['a', 'b'].map(side => <button key={side} onClick={() => setParams(old => { const p = new URLSearchParams(old); p.set(`map_${side}`, item.root); return p; })}>Use as {side.toUpperCase()}</button>)}</td></tr>)}</tbody></table></div>
    {!data.items.length && <p>No stored maps supplied on this page.</p>}
    <Pager next={data.next_cursor} cursorKey="map_cursor" resetKey={params.get('map_source_revision') ?? ''} />
  </>}</ReadState>;
}
function SelectedRoot({ root, against }: { root: string | null; against?: string }) {
  const [params, setParams] = useSearchParams();
  const selected = params.get('map_root') ?? root;
  if (!selected) return <p>No selected map supplied. Use Stored maps to choose an available root.</p>;
  return <MapDetail key={selected} root={selected} against={against} select={tab => setParams(old => { const p = new URLSearchParams(old); p.set('map_tab', tab); p.set('map_root', selected); return p; })} />;
}
function MapDetail({ root, against, select }: { root: string; against?: string; select: (tab: string) => void }) {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const tab = params.get('map_tab') ?? 'sections';
  const section = (params.get('map_section') ?? 'directories') as typeof mapSections[number];
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (!returnPosition(location.state)) focusBelowHeader(heading.current); }, [root, location.state]);
  return <section className="panel map-detail"><h2 ref={heading} tabIndex={-1}>Map root <code>{root}</code></h2>
    <InvestigationTabs label="Map detail" prefix="map-detail" active={tab} select={select} tabs={['sections', 'inputs', 'provenance'].map(id => ({ id, label: title(id) }))} />
    <div role="tabpanel" id={`map-detail-panel-${tab}`} aria-labelledby={`map-detail-tab-${tab}`}>
      {tab === 'inputs' ? <Inputs root={root} /> : <DetailBody key={root + tab + section} root={root} against={against} tab={tab} section={section} changeSection={value => setParams(old => { const p = new URLSearchParams(old); p.set('map_section', value); return p; })} />}
    </div>
  </section>;
}
function DetailBody({ root, against, tab, section, changeSection }: { root: string; against?: string; tab: string; section: typeof mapSections[number]; changeSection: (value: string) => void }) {
  const schema = StructuralDetailResponse.refine(value => value.data.summary.root === root, 'Map root binding mismatch').refine(value => !against || !value.data.freshness.against_commit || value.data.freshness.against_commit === against, 'Compared-against commit binding mismatch');
  const query = useMapRead(structuralMapRoute(root, { against, section: tab === 'sections' ? section : 'limits_and_omissions' }), schema, useCapability('maps').available);
  const data = query.data?.value.data;
  return <ReadState query={query}>{data && <>
    <p>{data.label}</p><SemanticValue value={data.summary.status} known={['AVAILABLE', 'CORRUPT']} /><Reasons values={data.summary.reasons} />
    <SemanticValue value={data.freshness.status} known={['CURRENT', 'STALE', 'UNKNOWN']} /><Reasons values={data.freshness.reasons} /><p>Compared against commit: <code>{data.freshness.against_commit ?? 'Not supplied'}</code></p>
    <p>Cut strings: {data.cut_strings} · Dropped fields: {data.dropped_fields}. Omitted or capped material remains unknown.</p>
    {tab === 'sections' ? <><label>Map section <select value={section} onChange={event => changeSection(event.target.value)}>{mapSections.map(value => <option key={value} value={value}>{title(value)}</option>)}</select></label><h3>{title(section)}</h3><Fields value={data.sections[section]} /></> : <><h3>Exact source and generator</h3><Fields value={data.summary} semantic={{ status: ['AVAILABLE', 'CORRUPT'], object_format: ['sha1', 'sha256'] }} /><h3>Freshness and metadata paths</h3><Fields value={data.freshness} /><h3>Limits and input identity</h3><Fields value={data.limits} /><Fields value={data.inputs} /></>}
  </>}</ReadState>;
}
function Inputs({ root }: { root: string }) {
  const [params] = useSearchParams();
  const schema = StructuralInputsResponse.refine(value => value.data.root === root, 'Input root binding mismatch');
  const query = useMapRead(mapInputsRoute(root, { limit: 50, cursor: params.get('map_input_cursor') ?? undefined }), schema, useCapability('maps').available);
  const data = query.data?.value.data;
  return <ReadState query={query}>{data && <><p>{data.label}</p><p>Recorded inputs · 50 per page · Cut strings: {data.cut_strings} · Dropped fields: {data.dropped_fields}</p><Fields value={data.items} /><Pager next={data.next_cursor} cursorKey="map_input_cursor" resetKey={root} /></>}</ReadState>;
}
function Compare() {
  const [params, setParams] = useSearchParams();
  const [a, setA] = useState(params.get('map_a') ?? '');
  const [b, setB] = useState(params.get('map_b') ?? '');
  const [error, setError] = useState('');
  const suppliedA = params.get('map_a') ?? '', suppliedB = params.get('map_b') ?? '';
  useEffect(() => { setA(suppliedA); setB(suppliedB); setError(''); }, [suppliedA, suppliedB]);
  return <><p>Choose both roots explicitly, or use the A/B controls in Stored maps. Editing these draft roots does not relabel a supplied comparison.</p><form noValidate onSubmit={event => { event.preventDefault(); if (!Sha256.safeParse(a).success || !Sha256.safeParse(b).success) { setError('Choose two complete map roots.'); focusBelowHeader(event.currentTarget.querySelector<HTMLInputElement>(!Sha256.safeParse(a).success ? '#map-root-a' : '#map-root-b')); return; } setError(''); setParams(old => { const p = new URLSearchParams(old); p.set('map_a', a); p.set('map_b', b); return p; }); }}>
    <label>Map A root <input id="map-root-a" value={a} aria-invalid={!!error && !Sha256.safeParse(a).success} aria-describedby={error ? 'map-compare-error' : undefined} onChange={event => setA(event.target.value)} /></label><label>Map B root <input id="map-root-b" value={b} aria-invalid={!!error && !Sha256.safeParse(b).success} aria-describedby={error ? 'map-compare-error' : undefined} onChange={event => setB(event.target.value)} /></label><button>Compare explicit roots</button>{error && <p id="map-compare-error" role="alert">{error}</p>}
  </form>{params.get('map_a') && params.get('map_b') && <Diff key={params.get('map_a')! + params.get('map_b')!} a={params.get('map_a')!} b={params.get('map_b')!} />}</>;
}
function Diff({ a, b }: { a: string; b: string }) {
  const [params, setParams] = useSearchParams();
  const section = (params.get('map_section') ?? 'directories') as typeof mapSections[number];
  const schema = MapDiffResponse.refine(value => value.data.a.root === a && value.data.b.root === b, 'Comparison root binding mismatch');
  const query = useMapRead(mapDiffRoute(a, b), schema, useCapability('maps').available);
  const data = query.data?.value.data;
  return <ReadState query={query}>{data && <><p>{data.label}</p><h2>Explicit comparison operands</h2><Fields value={{ a: data.a, b: data.b }} /><p>Supplied identical result: {String(data.identical)} · Cut strings: {data.cut_strings} · Dropped fields: {data.dropped_fields} · Dropped items: {data.dropped_items}</p><details><summary>Envelope differences</summary><Fields value={data.envelope} /></details><label>Comparison section <select value={section} onChange={event => setParams(old => { const p = new URLSearchParams(old); p.set('map_section', event.target.value); return p; })}>{mapSections.map(value => <option key={value} value={value}>{title(value)}</option>)}</select></label><h3>{title(section)}</h3>{data.sections[section].beyond_cap && <p className="preview-note">Changes beyond the supplied cap remain unknown.</p>}<Fields value={data.sections[section]} /></>}</ReadState>;
}
export function MapsPage() {
  const [params, setParams] = useSearchParams();
  const [against, setAgainst] = useState(params.get('map_against') ?? '');
  const [error, setError] = useState('');
  const suppliedAgainst = params.get('map_against') ?? '';
  useEffect(() => { setAgainst(suppliedAgainst); setError(''); }, [suppliedAgainst]);
  let presentation;
  try { presentation = mapPresentation(params); } catch (cause) { return <p role="alert">{cause instanceof Error ? cause.message : 'Invalid Maps presentation.'} No Maps request was sent.</p>; }
  return <><div className="page-heading"><div><h1>Maps</h1><p>Derived navigation context. Maps and candidate labels do not establish acceptance or block workflow.</p></div><CopyDashboardLink /></div><CapabilityGate name="maps">
    <form className="maps-against" noValidate onSubmit={event => { event.preventDefault(); if (against && !ObjectId.safeParse(against).success) { setError('Enter a complete commit identity.'); focusBelowHeader(event.currentTarget.querySelector('input')); return; } setError(''); setParams(old => { const p = new URLSearchParams(old); if (against) p.set('map_against', against); else p.delete('map_against'); return p; }); }}><label>Compare freshness against commit <input value={against} aria-invalid={!!error} aria-describedby={error ? 'map-against-error' : undefined} onChange={event => setAgainst(event.target.value)} placeholder="Full commit ID; blank uses supplied current commit" /></label><button>Apply commit</button>{error && <p id="map-against-error" role="alert">{error}</p>}</form>
    <InvestigationTabs label="Maps activity" prefix="maps" active={presentation.activity} tabs={[{ id: 'selected', label: 'Selected map' }, { id: 'stored', label: 'Stored maps' }, { id: 'compare', label: 'Compare maps' }]} select={activity => setParams(old => { const p = new URLSearchParams(old); p.set('map_activity', activity); return p; })} />
    <div className="panel maps-panel" role="tabpanel" id={`maps-panel-${presentation.activity}`} aria-labelledby={`maps-tab-${presentation.activity}`}>
      {presentation.activity === 'stored' ? <Stored /> : presentation.activity === 'compare' ? <Compare /> : <Overview against={presentation.against} />}
    </div>
  </CapabilityGate></>;
}
