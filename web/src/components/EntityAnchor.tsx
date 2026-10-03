import { CopyCli } from './CopyCli';
import { Link, useLocation } from 'react-router-dom';
import { dashboardEntityLink, navigationParams } from '../api/navigation';
import { useWorkspaceCollection } from './InvestigationWorkspace';
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
  workWorkspace = false,
}: {
  entity: { id: string; kind: string; title?: string | null };
  workWorkspace?: boolean;
}) {
  const location = useLocation();
  const capability = useCapability(
    capabilities[entity.kind] ?? '__unknown_entity',
  );
  const collection = useWorkspaceCollection();
  const workspace =
    (workWorkspace && entity.kind === 'work') ||
    (collection === 'work' &&
      ['work', 'ticket', 'story', 'epic'].includes(entity.kind)) ||
    (collection === 'runs' && entity.kind === 'invocation');
  // Cross-collection Work links carry demo identity, not source filters or selection.
  const search =
    workWorkspace && entity.kind === 'work' && collection !== 'work'
      ? navigationParams(new URLSearchParams(location.search)).toString()
      : location.search;
  const href = dashboardEntityLink(entity, search, workspace);
  const label = entity.title ?? entity.id;
  return href && capability.available ? (
    <span className="entity-with-cli">
      <Link to={href}>{label}</Link>
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
