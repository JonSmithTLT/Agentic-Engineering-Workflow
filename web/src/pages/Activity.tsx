import { useSearchParams } from 'react-router-dom';
import { CollectionView, Reasons } from '../components/ProjectionViews';
import { EntityAnchor } from '../components/EntityAnchor';
import { CopyDashboardLink } from '../components/CopyDashboardLink';
import { responseSchemas } from '../api/schema';
import { entityLink } from '../api/links';
import { historicalRequested } from '../api/navigation';

export function ActivityPage() {
  const [params] = useSearchParams();
  const valid = !historicalRequested(params) && params.getAll('cursor').length <= 1 && (!params.has('cursor') || !!params.get('cursor'));
  return (
    <CollectionView name="activity" title="Activity" path="/activity"
      description="Recorded activity supplied by AEW. Pages preserve source order; timestamps do not establish causation."
      schema={responseSchemas.ActivityListResponse} pageSize={50} historical automaticRevalidation={false} focusOnPageChange refreshFirstPage valid={valid}
      filterUI={<div className="activity-toolbar"><p className="muted">At most 50 records per page. First page loads the latest activity. Refresh page checks the displayed window; older cursors stay pinned.</p><CopyDashboardLink /></div>}
    >
      {items => <div className="activity-records">{items.map(item => (
        <article className="activity-record" data-testid="activity-record" aria-label={`Activity ${item.id}`} key={item.id}>
          <h3>{item.title}</h3>
          <dl className="activity-facts">
            <div><dt>Activity ID</dt><dd><code>{item.id}</code></dd></div>
            <div><dt>Occurred UTC</dt><dd><time dateTime={item.occurred_at}>{item.occurred_at}</time></dd></div>
            <div><dt>Subject</dt><dd><EntityAnchor entity={item.subject} />{!entityLink(item.subject) && <>
              {item.subject.title !== null && item.subject.title !== item.subject.id && <> · <code>{item.subject.id}</code></>}
              <p className="muted">No detail view available.</p>
            </>}</dd></div>
          </dl>
          {item.reason ? <details><summary>Supplied reason</summary><Reasons values={[item.reason]} /></details> : <p className="muted">No reason supplied.</p>}
        </article>
      ))}</div>}
    </CollectionView>
  );
}
