import { Link, useLocation } from 'react-router-dom';
import { navigationParams } from '../../navigation';
import { EntityAnchor } from '../../../components/EntityAnchor';
import { SemanticValue } from '../../../components/States';
type Ref = { id: string; kind: string; title: string | null };
const terminal = ['work_reference', 'evidence_reference', 'decision_reference', 'receipt_reference'];
/** Domain reference presentation is reusable outside comparison; routes remain explicit. */
export function ContextReferences({ values }: { values: Ref[] }) {
  const location = useLocation();
  return values.length ? <ul className="context-references">{values.map((ref, index) => {
    const params = navigationParams(new URLSearchParams(location.search)); params.set('view', 'journal'); params.set('selected', ref.id); params.set('panel', 'summary');
    return <li key={`${ref.kind}:${ref.id}:${index}`}>{ref.kind === 'journal' ? <Link to={`/knowledge?${params}`}>{ref.title ?? ref.id}</Link> : terminal.includes(ref.kind) ? <><code>{ref.id}</code>{ref.title && ref.title !== ref.id && <> · {ref.title}</>} <small>({ref.kind.replaceAll('_', ' ')}; reference only)</small></> : <EntityAnchor entity={ref} />}{ref.kind === 'journal' && <small> · Journal preview reference</small>}{!terminal.includes(ref.kind) && ref.kind !== 'journal' && !['work', 'invocation', 'evidence', 'knowledge', 'decision', 'fact', 'assumption', 'ticket', 'story', 'epic', 'history', 'audit'].includes(ref.kind) && <SemanticValue value={ref.kind} known={terminal} />}</li>;
  })}</ul> : <p>No references supplied.</p>;
}
