import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import manifest from '../../../../docs/design/w07-reuse.manifest.json';
import { useDashboard } from '../../../client/dashboard';
import { CopyDashboardLink } from '../../../components/CopyDashboardLink';
import { rememberReference, restoreReference, returnPosition } from '../../../components/reference-return';
import type { useComparisonSource } from '../investigation/session';
import { BoundPacketHost } from '../investigation/BoundPacketHost';
import { investigationSchemas } from '../investigation/schema';
import { PacketInspector } from '../investigation/PacketInspector';
import { ErrorState } from '../investigation/ui';
import { accessRefused } from '../../transport';
import { reuseManifestSchema, reuseItemIssue, type ReuseAssociation } from './reuse';

const supplied = reuseManifestSchema.safeParse(manifest);
export function associationFor(associationId: string, name: string, record: string, project: string) {
  return supplied.success ? supplied.data.associations.find(a => a.id === associationId &&
    a.origin.case === name && a.origin.record_id === record && a.origin.project_id === project) : undefined;
}
export function ContextAssociations({ name, record, visible }: { name: string; record: string; visible: boolean }) {
  const project = useDashboard().project.data?.value.project_id;
  const [params, setParams] = useSearchParams();
  const mappings = supplied.success ? supplied.data.associations.filter(a => a.origin.case === name && a.origin.record_id === record && a.origin.project_id === project) : [];
  return <details><summary>Context associations</summary>
    <p>Supplied associations; inspect the packet item and receipts for its reported disposition and stages. This preview is not a complete reuse history.</p>
    {!supplied.success ? <p role="alert">Context association manifest invalid.</p> : !mappings.length ? <p>No context association supplied for this preview.</p> : mappings.map(a => <AssociationLink key={a.id} association={a} visible={visible} open={() => {
      rememberReference(`reuse:${a.id}`);
      const p = new URLSearchParams(params); p.set('context_association', a.id);
      for (const k of ['packet_tab', 'packet_section', 'packet_disposition', 'packet_cursor']) p.delete(k);
      setParams(p, { state: { reuseOriginIndex: window.history.state?.idx } });
    }} />)}
  </details>;
}
function AssociationLink({ association: a, visible, open }: { association: ReuseAssociation; visible: boolean; open: () => void }) {
  const location = useLocation(), button = useRef<HTMLButtonElement>(null), restored = useRef(false);
  useLayoutEffect(() => {
    const position = returnPosition(location.state);
    if (!restored.current && visible && position?.reference === `reuse:${a.id}` && button.current) {
      const disclosure = button.current.closest('details'); if (disclosure) disclosure.open = true;
      restoreReference(position, button.current); restored.current = true;
    }
  }, [location.state, a.id, visible]);
  return <section><p><code>{a.id}</code> · Packet <code>{a.target.record_id}</code> · Source <code>{a.target.source_id}</code> · Snapshot <code>{a.target.snapshot_id}</code> · Invocation <code>{a.target.invocation_id}</code> · Run <code>{a.target.run_id ?? 'Not supplied'}</code></p>
    <button ref={button} data-context-association={a.id} onClick={open}>Inspect associated packet {a.target.record_id}</button></section>;
}
export function JournalPacketHost({ name, record, associationId }: { name: string; record: string; associationId: string }) {
  const project = useDashboard().project.data?.value.project_id, location = useLocation();
  const navigate = useNavigate(), [params, setParams] = useSearchParams();
  const originIndex = useRef(Number.isInteger(location.state?.reuseOriginIndex) && location.state.reuseOriginIndex >= 0 ? location.state.reuseOriginIndex : null);
  const association = project ? associationFor(associationId, name, record, project) : undefined;
  const back = () => {
    const now = window.history.state?.idx;
    if (originIndex.current !== null && now > originIndex.current) navigate(originIndex.current - now);
    else { const p = new URLSearchParams(params); for (const k of ['context_association', 'packet_tab', 'packet_section', 'packet_disposition', 'packet_cursor']) p.delete(k); p.set('panel', 'provenance'); setParams(p); }
  };
  return <><CopyDashboardLink />{!project ? <p role="status">Waiting for project bootstrap…</p> : !association ? <><button onClick={back}>Return to Journal</button><p role="alert">Context association unavailable or binding mismatch. No packet request sent.</p></> : <VerifiedAssociationHost key={`${associationId}:${name}:${project}`} association={association} back={back} />}</>;
}
function VerifiedAssociationHost({ association: a, back }: { association: ReuseAssociation; back: () => void }) {
  const binding = useMemo(() => a.target, [a]);
  return <BoundPacketHost owner={`journal-association:${a.id}`} name={a.target.case} binding={binding} back={back} backLabel="Back to Journal" render={query => <AssociationItemGate association={a} query={query} back={back} />} />;
}
function AssociationItemGate({ association: a, query, back }: { association: ReuseAssociation; query: ReturnType<typeof useComparisonSource>; back: () => void }) {
  const client = useQueryClient();
  const source = query.data?.value.data;
  const [proof, setProof] = useState<{ source: typeof source; error?: Error } | null>(null), [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!source) return;
    const controller = new AbortController();
    const route = `/packets/${encodeURIComponent(a.target.record_id)}/items?` + new URLSearchParams({ case: a.target.case, source_id: a.target.source_id, section: a.target.section, limit: '50', ...(a.target.cursor ? { cursor: a.target.cursor } : {}) });
    const schema = investigationSchemas.PacketItemListResponse.superRefine((value, ctx) => {
      const issue = reuseItemIssue(value.data.items, a);
      if (issue || value.data.items.some(i => i.packet_id !== a.target.record_id || i.source_id !== a.target.source_id)) ctx.addIssue({ code: 'custom', message: issue ?? 'Packet item binding mismatch' });
    });
    query.reader.get(route, schema, controller.signal).then(() => { if (!controller.signal.aborted) setProof({ source }); })
      .catch(error => { if (!controller.signal.aborted) {
        if (accessRefused(error)) {
          query.reader.clearRepresentations();
          for (const owned of client.getQueryCache().findAll({ predicate: q => q.queryKey[1] === query.reader.context.key('/sources') })) owned.setState({ data: undefined, error });
        }
        setProof({ source, error });
      } })
      .finally(() => query.reader.forget(route));
    return () => { controller.abort(); query.reader.forget(route); };
  }, [a, source, query.reader, retry, client]);
  if (query.error && !source) return <><button onClick={back}>Back to Journal</button><ErrorState error={query.error} retry={() => void query.refetch()} /></>;
  if (!source || proof?.source !== source) return <><button onClick={back}>Back to Journal</button><p role="status">Validating supplied context association…</p></>;
  if (proof.error) return <><button onClick={back}>Back to Journal</button><ErrorState error={proof.error} retry={() => setRetry(n => n + 1)} /></>;
  return <PacketInspector query={query} packetId={a.target.record_id} name={a.target.case} back={back} backLabel="Back to Journal" boundedItemPages />;
}
