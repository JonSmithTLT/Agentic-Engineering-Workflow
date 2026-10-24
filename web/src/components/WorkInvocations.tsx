import type { z } from 'zod';
import { Link, useLocation } from 'react-router-dom';
import { navigationParams } from '../api/navigation';
import type { work } from '../api/schema';
import { invocationRoles, invocationStatuses } from '../api/vocabulary';
import { useCapability, useDashboard } from '../client/dashboard';
import { EntityAnchor } from './EntityAnchor';
import { SemanticValue } from './States';

/** Uses already loaded, explicitly bound references; never scans Runs. */
export function WorkInvocations({ record, project }: {
  record: z.infer<typeof work>;
  project: string;
}) {
  const { overview } = useDashboard();
  const location = useLocation();
  const runsAvailable = useCapability('runs').available;
  const available = useCapability('overview').available;
  const source = available && overview.data?.value.project_id === project
    ? overview.data : undefined;
  const reported = source?.value.data.runs.filter((item) =>
    ['work', 'ticket', 'story', 'epic'].includes(item.work.kind) && item.work.id === record.id,
  ) ?? [];
  const references = record.related.filter((item) => item.kind === 'invocation');
  const ids = [...new Set([...references.map(item => item.id), ...reported.map(item => item.id)])];
  return (
    <section className="work-invocations" aria-label="Invocations for this work">
      <div className="panel-heading"><h2>Invocations</h2></div>
      <p className="muted">Supplied Work references and matching invocations from the bounded Overview summary. This is not a complete invocation history.</p>
      {source && <p className="muted">Overview revision <code>{source.value.control_revision}</code> · generated <time>{source.value.generated_at}</time></p>}
      {source && overview.isError && <p className="preview-note" role="status">Overview refresh failed. Invocation details below are last-known-good data.</p>}
      {ids.length ? <ul className="work-invocation-list">{ids.map(id => {
        const item = reported.find(value => value.id === id);
        const reference = references.find(value => value.id === id);
        return <li key={id}>
          <EntityAnchor entity={{ kind: 'invocation', id }} copyCli={false} />
          {reference?.title && reference.title !== id && <span>{reference.title}</span>}
          {item ? <><span>Role: <SemanticValue value={item.role} known={invocationRoles} /></span><span>Reported status: <SemanticValue value={item.status} known={invocationStatuses} /></span></> : <span className="muted">Role and status not supplied in this summary.</span>}
        </li>;
      })}</ul> : <p>No invocation references supplied here. Other invocations may exist.</p>}
      {runsAvailable && <p><Link to={'/runs?' + navigationParams(new URLSearchParams(location.search)).toString()}>Browse Runs</Link></p>}
    </section>
  );
}
