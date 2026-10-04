import { InvestigationWorkspace } from '../components/InvestigationWorkspace';
import { ComparisonEntry } from '../components/ComparisonEntry';
import { ExecutionEntry } from '../components/ExecutionEntry';
import { EvidenceEntry } from '../components/EvidenceEntry';
import { useSearchParams } from 'react-router-dom';
import {
  CollectionView,
  DetailView,
  Reasons,
  References,
} from '../components/ProjectionViews';
import { EntityAnchor } from '../components/EntityAnchor';
import { SemanticValue } from '../components/States';
import { SafeContent, JsonContent } from '../components/Content';
import { responseSchemas, id as identity } from '../api/schema';
import {
  invocationStatuses,
  invocationRoles,
  harnessStatuses,
  evidenceKinds,
  evidenceResults,
  evidenceCurrentness,
  decisionTypes,
} from '../api/vocabulary';
const knowledgeKinds = ['decision', 'fact', 'assumption'];
export function RunsPage() {
  return (
    <InvestigationWorkspace
      collection="runs"
      results={<RunsResultsPage />}
      detail={(id, visible) => (
        <RunDetailPage recordId={id} displayed={visible} />
      )}
    />
  );
}
function RunsResultsPage() {
  return (
    <><ExecutionEntry />
    <CollectionView
      name="runs"
      title="Runs"
      description="Invocations and the harness runs they contain."
      path="/runs"
      schema={responseSchemas.InvocationListResponse}
    >
      {(items) => (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Invocation</th>
                <th>Role</th>
                <th>Status</th>
                <th>Work</th>
                <th>Harness runs</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <EntityAnchor entity={{ id: r.id, kind: 'invocation' }} />
                  </td>
                  <td>
                    <SemanticValue value={r.role} known={invocationRoles} />
                  </td>
                  <td>
                    <SemanticValue
                      value={r.status}
                      known={invocationStatuses}
                    />
                  </td>
                  <td>
                    <EntityAnchor entity={r.work} />
                  </td>
                  <td>
                    {r.runs.length
                      ? `${r.runs.length} supplied`
                      : 'No harness runs supplied'}
                  </td>
                  <td>
                    <time>{r.created_at}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </CollectionView></>
  );
}
export function RunDetailPage({
  recordId,
  displayed = true,
}: { recordId?: string; displayed?: boolean } = {}) {
  return (
    <DetailView
      name="runs"
      title="Runs"
      path="/runs"
      schema={responseSchemas.InvocationResponse}
      recordId={recordId}
      displayed={displayed}
    >
      {(r) => (
        <>
          <div className="page-heading">
            <div>
              <h1>{r.id}</h1>
              <ComparisonEntry invocation={r.id} />
              <ExecutionEntry invocation={r.id} displayed={displayed} />
              <p>
                <SemanticValue value={r.role} known={invocationRoles} /> ·{' '}
                <EntityAnchor entity={r.work} />
              </p>
            </div>
            <SemanticValue value={r.status} known={invocationStatuses} />
          </div>
          <div className="detail-grid">
            <section className="panel detail-main record-main">
              <h2>Invocation context</h2>
              <SafeContent {...r.summary} />
              <h2>Harness runs</h2>
              {r.runs.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Run</th>
                        <th>Harness</th>
                        <th>Kind</th>
                        <th>Status</th>
                        <th>Authority</th>
                        <th>Launched</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.runs.map((run) => (
                        <tr key={run.id}>
                          <td>
                            <code>{run.id}</code>
                          </td>
                          <td>{run.harness}</td>
                          <td>
                            <SemanticValue
                              value={run.kind}
                              known={['launch', 'relaunch']}
                            />
                          </td>
                          <td>
                            <SemanticValue
                              value={run.status}
                              known={harnessStatuses}
                            />
                          </td>
                          <td>
                            <span>{run.authority}</span>
                          </td>
                          <td>
                            <time>{run.launched_at}</time>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty">
                  No harness runs supplied for this invocation.
                </p>
              )}
              <h2>Backend reasons</h2>
              <Reasons values={r.reasons} />
            </section>
            <aside className="panel facts">
              <h2>Evidence</h2>
              <References values={r.evidence} />
              <h2>Invocation metadata</h2>
              <dl>
                <dt>Created</dt>
                <dd>
                  <time>{r.created_at}</time>
                </dd>
                <dt>Work</dt>
                <dd>
                  <EntityAnchor entity={r.work} />
                </dd>
              </dl>
            </aside>
          </div>
        </>
      )}
    </DetailView>
  );
}
export function EvidencePage() {
  const [params, setParams] = useSearchParams();
  const work = params.get('work') ?? '';
  return (
    <CollectionView
      name="evidence"
      title="Evidence"
      description="Claims, reported results and the snapshots they evaluate."
      path="/evidence"
      schema={responseSchemas.EvidenceListResponse}
      filters={['work']}
      valid={!work || identity.safeParse(work).success}
      filterUI={
        <div className="filter-bar"><EvidenceEntry />
          <label>
            Work ID
            <input
              aria-label="Evidence work filter"
              value={work}
              placeholder="All work"
              onChange={(e) =>
                setParams((old) => {
                  const p = new URLSearchParams(old);
                  if (e.target.value) p.set('work', e.target.value);
                  else p.delete('work');
                  p.delete('cursor');
                  return p;
                })
              }
            />
          </label>
        </div>
      }
    >
      {(items) => (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Evidence</th>
                <th>Kind</th>
                <th>Subject</th>
                <th>Result</th>
                <th>Currentness</th>
                <th>Disposition</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td>
                    <EntityAnchor entity={{ id: e.id, kind: 'evidence' }} />
                  </td>
                  <td>
                    <SemanticValue value={e.kind} known={evidenceKinds} />
                  </td>
                  <td>
                    <EntityAnchor entity={e.subject} />
                  </td>
                  <td>
                    <SemanticValue value={e.result} known={evidenceResults} />
                  </td>
                  <td>
                    <SemanticValue
                      value={e.currentness}
                      known={evidenceCurrentness}
                    />
                  </td>
                  <td>
                    {e.requires_disposition ? 'Required' : 'Not required'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </CollectionView>
  );
}
export function EvidenceDetailPage() {
  return (
    <DetailView
      name="evidence"
      title="Evidence"
      path="/evidence"
      schema={responseSchemas.EvidenceResponse}
    >
      {(e) => (
        <>
          <div className="page-heading">
            <div>
              <h1>{e.id}</h1>
              <EvidenceEntry id={e.id} />
              <p>
                <SemanticValue value={e.kind} known={evidenceKinds} /> ·{' '}
                <EntityAnchor entity={e.subject} />
              </p>
            </div>
            <div>
              <SemanticValue value={e.result} known={evidenceResults} />{' '}
              <SemanticValue
                value={e.currentness}
                known={evidenceCurrentness}
              />
            </div>
          </div>
          {e.currentness !== 'CURRENT' && (
            <p className="preview-note" role="note">
              AEW reports {e.currentness} evidence. Do not treat this record as
              current evidence.
            </p>
          )}
          <div className="detail-grid">
            <section className="panel detail-main record-main">
              <h2>Claim</h2>
              <SafeContent {...e.claim} />
              <h2>Evidence body</h2>
              <SafeContent {...e.body} />
              <h2>Findings</h2>
              <Reasons values={e.findings} />
              <h2>Deviations</h2>
              <Reasons values={e.deviations} />
            </section>
            <aside className="panel facts">
              <h2>Bindings and producer</h2>
              <dl>
                <dt>Disposition</dt>
                <dd>
                  {e.requires_disposition
                    ? 'Required by AEW'
                    : 'Not required by AEW'}
                </dd>
                <dt>Producer invocation</dt>
                <dd>
                  <EntityAnchor
                    entity={{
                      id: e.bindings.producer.invocation,
                      kind: 'invocation',
                    }}
                  />
                </dd>
                <dt>Harness run</dt>
                <dd>
                  <code>{e.bindings.producer.run ?? 'Not supplied'}</code>
                </dd>
                <dt>Producer role</dt>
                <dd>
                  <SemanticValue
                    value={e.bindings.producer.role}
                    known={invocationRoles}
                  />
                </dd>
                <dt>Harness</dt>
                <dd>{e.bindings.producer.harness ?? 'Not supplied'}</dd>
                <dt>Model / provider</dt>
                <dd>
                  {e.bindings.producer.model ?? 'Not supplied'} /{' '}
                  {e.bindings.producer.provider ?? 'Not supplied'}
                </dd>
              </dl>
              <details>
                <summary>Evaluated snapshot and plan bindings</summary>
                <JsonContent
                  value={{
                    evaluated_snapshot: e.bindings.evaluated_snapshot,
                    plan_revision: e.bindings.plan_revision,
                  }}
                />
              </details>
              <h2>Provenance</h2>
              <References values={e.provenance} />
            </aside>
          </div>
        </>
      )}
    </DetailView>
  );
}
export function KnowledgePage() {
  return (
    <CollectionView
      name="knowledge"
      title="Knowledge"
      description="Durable decisions, facts and assumptions, grouped within the loaded page."
      path="/knowledge"
      schema={responseSchemas.KnowledgeListResponse}
      historical
    >
      {(items) =>
        [...new Set(items.map((k) => k.kind))].map((kind) => (
          <section className="knowledge-group" key={kind}>
            <h3>
              <SemanticValue value={kind} known={knowledgeKinds} />
            </h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Record</th>
                    <th>Title</th>
                    <th>State</th>
                    <th>Decision type</th>
                  </tr>
                </thead>
                <tbody>
                  {items
                    .filter((k) => k.kind === kind)
                    .map((k) => (
                      <tr key={k.id}>
                        <td>
                          <EntityAnchor
                            entity={{ id: k.id, kind: 'knowledge' }}
                          />
                        </td>
                        <td>
                          <EntityAnchor
                            entity={{
                              id: k.id,
                              kind: 'knowledge',
                              title: k.title,
                            }}
                          />
                        </td>
                        <td>
                          <SemanticValue value={k.state} known={[]} />
                        </td>
                        <td>
                          <SemanticValue
                            value={k.decision_type}
                            known={decisionTypes}
                          />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      }
    </CollectionView>
  );
}
export function KnowledgeDetailPage() {
  return (
    <DetailView
      name="knowledge"
      title="Knowledge"
      path="/knowledge"
      schema={responseSchemas.KnowledgeResponse}
      historical
    >
      {(k) => (
        <>
          <div className="page-heading">
            <div>
              <SemanticValue value={k.kind} known={knowledgeKinds} />
              <h1>{k.title}</h1>
              <code>{k.id}</code>
            </div>
            <SemanticValue value={k.state} known={[]} />
          </div>
          <div className="detail-grid">
            <section className="panel detail-main record-main">
              <h2>Record</h2>
              <SafeContent {...k.body} />
              <h2>Backend reasons</h2>
              <Reasons values={k.reasons} />
            </section>
            <aside className="panel facts">
              <h2>Provenance</h2>
              <References values={k.provenance} />
              <h2>Decision type</h2>
              <SemanticValue value={k.decision_type} known={decisionTypes} />
              <p className="muted">
                State is reported by AEW. No Knowledge-state vocabulary is
                declared by this contract.
              </p>
            </aside>
          </div>
        </>
      )}
    </DetailView>
  );
}
