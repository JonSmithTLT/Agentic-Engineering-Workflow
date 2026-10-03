import { CopyCli } from './CopyCli';
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
  audit: 'history',
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
  const params = new URLSearchParams(location.search);
  const context = new URLSearchParams();
  if (import.meta.env.MODE === 'demo')
    for (const key of ['fixture', 'fault']) {
      const value = params.get(key);
      if (value) context.set(key, value);
    }
  const search = context.size ? '?' + context.toString() : '';
  return href && capability.available ? (
    <span className="entity-with-cli">
      <Link to={href + search}>{label}</Link>
      <CopyCli kind={entity.kind} id={entity.id} />
    </span>
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
