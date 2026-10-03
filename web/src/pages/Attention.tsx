import { RecordInspection } from '../components/Investigation';
import { CollectionView, Reasons } from '../components/ProjectionViews';
import { responseSchemas } from '../api/schema';
import { EntityAnchor } from '../components/EntityAnchor';
import { SafeContent } from '../components/Content';
import { SemanticValue, Unavailable } from '../components/States';
import { CapabilityGate, PageSnapshot } from '../client/dashboard';
export function AttentionPage() {
  return (
    <CollectionView
      name="action_projection"
      title="Attention"
      description="Decisions, blockers, required findings and anomalies reported by AEW."
      path="/attention"
      schema={responseSchemas.AttentionListResponse}
    >
      {(items, projection) => (
        <div className="attention-records">
          {items.map((a) => (
            <article key={a.id} className="attention-record">
              <RecordInspection
                kind="attention"
                record={a}
                source={projection}
              />
              <div className="attention-record-heading">
                <div>
                  <h3>{a.title}</h3>
                  <code>{a.id}</code>
                </div>
                <SemanticValue value={a.severity} known={[]} />
              </div>
              <p>
                <SemanticValue
                  value={a.kind}
                  known={[
                    'decision_required',
                    'blocker',
                    'required_finding',
                    'anomaly',
                  ]}
                />{' '}
                · <EntityAnchor entity={a.subject} />
              </p>
              <SafeContent {...a.summary} />
              <details>
                <summary>Backend reasons</summary>
                <Reasons values={a.reasons} />
              </details>
              <p className="muted">
                First seen <time>{a.first_seen_at}</time>
              </p>
            </article>
          ))}
        </div>
      )}
    </CollectionView>
  );
}
export function QueuePage() {
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Queue</h1>
          <p>Inspection of queue state when supported by AEW.</p>
        </div>
      </div>
      <PageSnapshot />
      <CapabilityGate name="queue">
        <Unavailable explanation="This API contract has no queue read projection. A main-line contract amendment is required before queue state, custody, validation or publication mode can be displayed." />
      </CapabilityGate>
    </>
  );
}
