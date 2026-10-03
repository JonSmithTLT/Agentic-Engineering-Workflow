import { ReceiptCard } from './ReceiptCard';
import { useEffect, useRef, useMemo } from 'react';
import { useProjection } from '../../../client/queries';
import { SourceStrip } from '../../../components/Investigation';
import { Pager } from '../../../components/ProjectionViews';
import { SafeContent } from '../../../components/Content';
import { SemanticValue } from '../../../components/States';
import { InvestigationTabs, focusBelowHeader } from '../../../components/InvestigationTabs';
import { ContextReferences as References } from './ContextReferences';
import { useControls, ErrorState } from './ui';
import { investigationSchemas, packetBindingIssue, knownReceiptTypes, knownDispositions, knownExplanationStates, type Packet } from './schema';
import type { useComparisonSource } from './session';
type SourceQuery = ReturnType<typeof useComparisonSource>;
export const packetTabs = [{ id: 'contents', label: 'Contents' }, { id: 'selection', label: 'Selection & budget' }, { id: 'receipts', label: 'Receipts' }, { id: 'provenance', label: 'Provenance' }];
function PacketItems({ packet, reader, name, selection }: { packet: Packet; reader: SourceQuery['reader']; name: string; selection: boolean }) {
  const { params, update } = useControls(), section = params.get('packet_section') ?? '', disposition = params.get('packet_disposition') ?? '';
  const route = `/packets/${encodeURIComponent(packet.id)}/items?` + new URLSearchParams({ case: name, source_id: packet.source_id, limit: '50', ...(section ? { section } : {}), ...(disposition ? { disposition } : {}), ...(params.get('packet_cursor') ? { cursor: params.get('packet_cursor')! } : {}) });
  const schema = useMemo(() => investigationSchemas.PacketItemListResponse.superRefine((value, ctx) => { if (value.data.items.some(i => i.packet_id !== packet.id || i.source_id !== packet.source_id || (packet.sections_complete && !packet.sections.some(s => s.id === i.section)))) ctx.addIssue({ code: 'custom', message: 'Packet item binding mismatch' }); }), [packet]);
  const query = useProjection(route, schema, 'history', true, true, reader, false);
  const issue = query.data?.value.data.items.some(i => i.packet_id !== packet.id || i.source_id !== packet.source_id || (packet.sections_complete && !packet.sections.some(s => s.id === i.section))) ? 'Packet item binding mismatch' : undefined;
  return <><div className="filter-bar"><label>Section<select value={section} onChange={event => update({ packet_section: event.target.value, packet_cursor: null })}><option value="">All sections</option>{packet.sections.map(s => <option key={s.id} value={s.id}>{s.title} · {s.count ?? 'Count not supplied'}</option>)}</select></label><label>Disposition<select value={disposition} onChange={event => update({ packet_disposition: event.target.value, packet_cursor: null })}><option value="">All dispositions</option>{knownDispositions.map(s => <option key={s}>{s}</option>)}</select></label></div>
    {!packet.sections_complete && <p className="preview-note">Section summaries are incomplete.</p>}
    {(query.error || issue) && <ErrorState error={issue ? new Error(issue) : query.error} retry={() => void query.refetch()} />}
    {query.data && !issue ? <><ul className="packet-items">{query.data.value.data.items.map(item => <li className="panel" key={item.id}><h3><code>{item.reference.id}</code> · {item.section}</h3><References values={[item.reference]} /><p><SemanticValue value={item.disposition} known={knownDispositions} /> · Source revision: {item.source_revision ?? 'Not supplied'}</p>
      {selection ? <><SemanticValue value={item.explanation.state} known={knownExplanationStates} /><p>{item.explanation.state === 'SUPPLIED' && item.explanation.text ? item.explanation.text : 'No selection explanation supplied.'}</p></> : <>{item.excerpt_scope && <p className="muted">{item.excerpt_scope}</p>}{item.excerpt ? <SafeContent {...item.excerpt} /> : <p>No excerpt supplied.</p>}{item.excerpt_truncated && <p className="preview-note">Supplied excerpt is truncated.</p>}</>}</li>)}</ul>
      {!query.data.value.data.items.length && <p>No packet items supplied for this filter.</p>}<Pager next={query.data.value.data.next_cursor} cursorKey="packet_cursor" resetKey={`${packet.source_id}:${packet.id}:${section}:${disposition}:${name}`} />
      {query.error && <p role="status">STALE / DISCONNECTED — showing valid prior item page.</p>}</> : !query.error && !issue && <p role="status">Loading packet items…</p>}
  </>;
}
export function PacketInspector({ query, packetId, name, back }: { query: SourceQuery; packetId: string; name: string; back: () => void }) {
  const { params, update } = useControls(), source = query.data?.value.data, tab = params.get('packet_tab') ?? 'contents';
  const association = source?.packets.find(p => p.id === packetId);
  const route = `/packets/${encodeURIComponent(packetId)}?` + new URLSearchParams({ case: name, source_id: source?.id ?? '' });
  const schema = useMemo(() => investigationSchemas.PacketResponse.superRefine((value, ctx) => { const issue = source ? packetBindingIssue(value.data, source) : 'Source binding unavailable'; if (value.data.id !== packetId || issue) ctx.addIssue({ code: 'custom', message: issue ?? 'Packet identity mismatch' }); }), [source, packetId]);
  const packetQuery = useProjection(route, schema, 'history', !!association, true, query.reader, false);
  const packet = packetQuery.data?.value.data, issue = packet && source ? packetBindingIssue(packet, source) : undefined;
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (packet && !issue) focusBelowHeader(heading.current); }, [packetId, !!packet, issue]);
  return <section className="packet-inspector"><button onClick={back}>Back to comparison</button><h2 ref={heading} tabIndex={-1}>Context packet {packetId}</h2>
    {query.error && <ErrorState error={query.error} retry={() => void query.refetch()} />}
    {source && !association && <p role="alert">Packet is not supplied for this source. No packet request sent.</p>}
    {(packetQuery.error || issue) && <ErrorState error={issue ? new Error(issue) : packetQuery.error} retry={() => void packetQuery.refetch()} />}
    {packet && !issue && <><p><code>{packet.source_id}</code> · <code>{packet.invocation_id}</code> · <code>{packet.run_id ?? 'Invocation-level'}</code> · <code>{packet.snapshot_id ?? 'Current source'}</code></p>
      <p className="scope-note">Prepared context ≠ delivered context ≠ output citation ≠ evaluated benefit. No attention or influence is inferred.</p>
      {packetQuery.error && <p role="status">STALE / DISCONNECTED — displaying valid previous packet.</p>}
      <InvestigationTabs prefix="packet" label="Packet sections" tabs={packetTabs} active={tab} select={id => update({ packet_tab: id })} />
      <div role="tabpanel" id={`packet-panel-${tab}`} aria-labelledby={`packet-tab-${tab}`}>
        {(tab === 'contents' || tab === 'selection') && <>{tab === 'selection' && <section className="panel"><h3>Supplied accounting</h3>{packet.accounting.length ? <div className="table-scroll"><table><thead><tr><th>Unit</th><th>Amount / limit</th><th>Estimator</th><th>Tokenizer</th></tr></thead><tbody>{packet.accounting.map((a, i) => <tr key={i}><td><SemanticValue value={a.unit} known={['TOKENS', 'BYTES']} /></td><td>{a.amount ?? 'Not supplied'} / {a.limit ?? 'Not supplied'}</td><td>{a.estimator_id ?? 'Not supplied'}</td><td>{a.tokenizer_id ?? 'Not supplied'}</td></tr>)}</tbody></table></div> : <p>No accounting supplied.</p>}<p>Policy: {packet.policy_id ?? 'Not supplied'} · Trigger: {packet.trigger ?? 'Not supplied'}</p></section>}<PacketItems packet={packet} reader={query.reader} name={name} selection={tab === 'selection'} /></>}
        {tab === 'receipts' && <>{!packet.receipts_complete && <p className="preview-note">Receipt projection is incomplete; no stage can be treated as an exhaustive history.</p>}{[['PREPARATION', 'Preparation', 'No preparation receipt supplied.'], ['DELIVERY', 'Delivery acknowledgment', 'No delivery receipt supplied.'], ['CITATION', 'Output citations', 'No output citation receipt supplied.'], ['BENEFIT', 'Benefit evaluations', 'No benefit evaluation supplied.']].map(([type, title, absent]) => <section className="panel" key={type}><h3>{title}</h3>{packet.receipts.filter(r => r.type === type).length ? packet.receipts.filter(r => r.type === type).map(r => <ReceiptCard key={r.id} receipt={r} />) : <p>{absent}</p>}</section>)}{packet.receipts.filter(r => !knownReceiptTypes.includes(r.type)).map(r => <ReceiptCard key={r.id} receipt={r} />)}</>}
        {tab === 'provenance' && <section className="panel"><dl><dt>Prepared UTC</dt><dd>{packet.prepared_at ?? 'Not supplied'}</dd><dt>Supplied fingerprint</dt><dd><code>{packet.fingerprint ?? 'Not supplied'}</code></dd><dt>Producer</dt><dd>{packet.producer ? `${packet.producer.id} · ${packet.producer.role ?? 'Role not supplied'}` : 'Not supplied'}</dd><dt>Source revision</dt><dd>{packet.source_revision ?? 'Not supplied'}</dd><dt>Environment</dt><dd>{packet.environment.join(' · ') || 'Not supplied'}</dd></dl><h3>Canonical references</h3><References values={packet.canonical_references} /><p>Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.</p><details><summary>Packet response metadata</summary><SourceStrip source={packetQuery.data!} failed={!!packetQuery.error} readSnapshot={query.reader.context.identity.snapshot} /></details></section>}
      </div></>}
    {!packet && !packetQuery.error && !query.error && association && <p role="status">Loading packet…</p>}
  </section>;
}
