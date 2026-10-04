import { EvidenceReference } from '../evidence/Reference';
import { investigationDigest } from '../evidence/fixtures';
import { Link, useLocation } from 'react-router-dom';
import { useLayoutEffect, useRef } from 'react';
import { rememberReference, restoreReference, returnPosition } from './return-focus';
import { navigationParams } from '../../navigation';
import { EntityAnchor } from '../../../components/EntityAnchor';
type Ref = { id: string; kind: string; title: string | null };
const terminal = ['work_reference', 'evidence_reference', 'decision_reference', 'receipt_reference'];
/** Domain reference presentation is reusable outside comparison; routes remain explicit. */
export function ContextReferences({ values, evidenceOrigin }: { values: Ref[]; evidenceOrigin?: { case: string; record_id: string; item_id: string | null; role: string; source_id: string; snapshot_id: string | null; visibility_scope: string } }) {
  const location = useLocation();
  const list = useRef<HTMLUListElement>(null), restored = useRef(false);
  useLayoutEffect(() => {
    const position = returnPosition(location.state);
    const target = position && Array.from(list.current?.querySelectorAll<HTMLAnchorElement>('[data-context-reference]') ?? []).find(el => el.dataset.contextReference === position.reference);
    if (!restored.current && position && target) { restoreReference(position, target); restored.current = true; }
  }, [location.state, values]);
  return values.length ? <ul ref={list} className="context-references">{values.map((ref, index) => {
    const params = navigationParams(new URLSearchParams(location.search)); params.set('view', 'journal'); params.set('selected', ref.id); params.set('panel', 'summary');
    return <li key={`${ref.kind}:${ref.id}:${index}`}>{ref.kind === 'evidence_reference' && evidenceOrigin ? <EvidenceReference origin={{contract:investigationDigest,...evidenceOrigin,kind:ref.kind,evidence_id:ref.id}}><code>{ref.id}</code>{ref.title && ref.title !== ref.id && <> · {ref.title}</>}</EvidenceReference> : ref.kind === 'journal' ? <Link data-context-reference={`${ref.kind}:${ref.id}`} onClick={event => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) rememberReference(`${ref.kind}:${ref.id}`); }} to={`/knowledge?${params}`}>{ref.title ?? ref.id}</Link> : terminal.includes(ref.kind) ? <><code>{ref.id}</code>{ref.title && ref.title !== ref.id && <> · {ref.title}</>} <small>({ref.kind.replaceAll('_', ' ')}; reference only)</small></> : <EntityAnchor entity={ref} />}{ref.kind === 'journal' && <small> · Journal preview reference</small>}</li>;
  })}</ul> : <p>No references supplied.</p>;
}
