import { Link, useLocation } from 'react-router-dom';
import { entityLink } from '../api/links';
import { SemanticValue } from './States';
import { useCapability } from '../client/dashboard';
const capabilities: Record<string, string> = {
  epic: 'work',
  story: 'work',
  ticket: 'work',
  work: 'work',
  invocation: 'runs',
  evidence: 'evidence',
  decision: 'knowledge',
  fact: 'knowledge',
  assumption: 'knowledge',
  knowledge: 'knowledge',
  history: 'history',
};
export function EntityAnchor({
  entity,
}: {
  entity: { id: string; kind: string; title?: string | null };
}) {
  const location = useLocation();
  const capability = useCapability(
    capabilities[entity.kind] ?? '__unknown_entity',
  );
  const href = entityLink(entity);
  const label = entity.title ?? entity.id;
  return href && capability.available ? (
    <Link to={href + location.search}>{label}</Link>
  ) : (
    <span title={capability.explanation}>
      {label}
      {!href && (
        <>
          {' '}
          ·{' '}
          <SemanticValue
            value={entity.kind}
            known={Object.keys(capabilities)}
          />
        </>
      )}
    </span>
  );
}
