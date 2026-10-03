import { useSearchParams } from 'react-router-dom';
import {
  CollectionView,
  DetailView,
  Pager,
  Reasons,
} from '../components/ProjectionViews';
import { EntityAnchor } from '../components/EntityAnchor';
import { SemanticValue, LoadError } from '../components/States';
import { JsonContent } from '../components/Content';
import {
  CapabilityGate,
  useCapability,
  PageSnapshot,
  ProjectionMetadata,
} from '../client/dashboard';
import { useProjection } from '../client/queries';
import { responseSchemas, timestamp } from '../api/schema';
import {
  historyKinds,
  trustSources,
  annotationRelations,
  historyLinkRelations,
  workStates,
} from '../api/vocabulary';
function HistoricalTarget({ target }: { target: string }) {
  return (
    <span className="history-reference">
      <code>{target}</code>
      <EntityAnchor
        entity={{ id: target, kind: 'work', title: 'Work lookup' }}
      />
      <EntityAnchor
        entity={{ id: target, kind: 'history', title: 'History lookup' }}
      />
    </span>
  );
}
function HistoryLinkTarget({
  relation,
  target,
}: {
  relation: string;
  target: string;
}) {
  if (relation === 'invocations')
    return <EntityAnchor entity={{ id: target, kind: 'invocation' }} />;
  if (relation === 'evidence')
    return <EntityAnchor entity={{ id: target, kind: 'evidence' }} />;
  if (['depends_on', 'moved_to', 'audit_finding'].includes(relation))
    return <HistoricalTarget target={target} />;
  // Tokens have no credential page; commits and unknown target types stay text.
  return <code>{target}</code>;
}
function HistoricalWarning() {
  return (
    <p className="preview-note" role="note">
      Historical references only. Archived records are never current evidence.
    </p>
  );
}
export function IntegrityPanel() {
  const available = useCapability('integrity').available;
  const query = useProjection(
    '/history/integrity',
    responseSchemas.IntegrityResponse,
    'history',
    available,
  );
  const data = query.data?.value.data;
  return (
    <section className="panel integrity-panel">
      <div className="panel-heading">
        <h2>History integrity</h2>
      </div>
      <CapabilityGate name="integrity">
        <PageSnapshot queries={[query]} />
        {!data ? (
          query.isError ? (
            <LoadError
              message={query.error.message}
              retry={() => {
                void query.refetch();
              }}
            />
          ) : (
            <p role="status">Loading integrity projection…</p>
          )
        ) : (
          <>
            <p>
              Backend audit status:{' '}
              <SemanticValue value={data.status} known={[]} />
            </p>
            <dl className="integrity-facts">
              <dt>Current root count</dt>
              <dd>{data.current_root.count}</dd>
              <dt>Unverified backlog</dt>
              <dd>{data.backlog}</dd>
              <dt>Oldest unverified record</dt>
              <dd>{data.oldest_unverified_at ?? 'Not supplied'}</dd>
              <dt>Last audit</dt>
              <dd>
                {data.last_audit ? (
                  <EntityAnchor entity={data.last_audit} />
                ) : (
                  'Not supplied'
                )}
              </dd>
            </dl>
            <div className="audit-roots">
              <section>
                <h3>Current root</h3>
                <JsonContent value={data.current_root} />
              </section>
              <section>
                <h3>Verified root</h3>
                {data.verified ? (
                  <JsonContent value={data.verified} />
                ) : (
                  <p>No verified root supplied.</p>
                )}
              </section>
              <section>
                <h3>Last full audit</h3>
                {data.last_full ? (
                  <JsonContent value={data.last_full} />
                ) : (
                  <p>No full audit supplied.</p>
                )}
              </section>
            </div>
            <Reasons values={data.reasons} />
            <button
              onClick={() => {
                void query.refetch();
              }}
            >
              Refresh integrity
            </button>
            {query.isError && (
              <LoadError
                message={query.error.message}
                retry={() => {
                  void query.refetch();
                }}
              />
            )}
            <ProjectionMetadata record={query.data!} />
          </>
        )}
      </CapabilityGate>
    </section>
  );
}
export function HistoryPage() {
  const [params, setParams] = useSearchParams();
  const since = params.get('since') ?? '',
    until = params.get('until') ?? '';
  const valid =
    (!since || timestamp.safeParse(since).success) &&
    (!until || timestamp.safeParse(until).success) &&
    (!since || !until || Date.parse(since) <= Date.parse(until));
  function change(key: string, value: string) {
    setParams((old) => {
      const p = new URLSearchParams(old);
      if (value) p.set(key, value);
      else p.delete(key);
      p.delete('cursor');
      return p;
    });
  }
  return (
    <>
      <CollectionView
        name="history"
        title="History"
        description="Bounded archive manifests, lineage and annotations. Refresh manually or on focus."
        path="/history"
        schema={responseSchemas.HistoryListResponse}
        historical
        filters={['kind', 'since', 'until']}
        valid={valid}
        filterUI={
          <>
            <HistoricalWarning />
            <div className="filter-bar">
              <label>
                Kind
                <select
                  aria-label="History kind filter"
                  value={params.get('kind') ?? ''}
                  onChange={(e) => change('kind', e.target.value)}
                >
                  <option value="">All kinds</option>
                  {params.get('kind') &&
                    !historyKinds.includes(
                      params.get('kind') as (typeof historyKinds)[number],
                    ) && <option>{params.get('kind')}</option>}
                  {historyKinds.map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </label>
              <label>
                Since (UTC)
                <input
                  aria-label="History since"
                  placeholder="2026-10-02T00:00:00Z"
                  value={since}
                  onChange={(e) => change('since', e.target.value)}
                />
              </label>
              <label>
                Until (UTC)
                <input
                  aria-label="History until"
                  placeholder="2026-10-02T23:59:59Z"
                  value={until}
                  onChange={(e) => change('until', e.target.value)}
                />
              </label>
            </div>
          </>
        }
      >
        {(items) => (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Sequence</th>
                  <th>Record</th>
                  <th>Title</th>
                  <th>Kind</th>
                  <th>Trust source</th>
                  <th>Recorded</th>
                  <th>Content hash</th>
                </tr>
              </thead>
              <tbody>
                {items.map((h) => (
                  <tr key={h.seq}>
                    <td>{h.seq}</td>
                    <td>
                      <EntityAnchor entity={{ id: h.id, kind: 'history' }} />
                    </td>
                    <td>{h.title ?? 'No title supplied'}</td>
                    <td>
                      <SemanticValue value={h.kind} known={historyKinds} />
                    </td>
                    <td>
                      <SemanticValue value={h.source} known={trustSources} />
                    </td>
                    <td>
                      <time>{h.at}</time>
                    </td>
                    <td>
                      <code title={h.sha256}>{h.sha256.slice(0, 12)}…</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CollectionView>
      <IntegrityPanel />
    </>
  );
}
export function HistoryDetailPage() {
  const [params] = useSearchParams();
  const query = new URLSearchParams({ annotations_limit: '100' });
  const cursor = params.get('annotations_cursor');
  if (cursor) query.set('annotations_cursor', cursor);
  return (
    <DetailView
      name="history"
      title="History"
      path="/history"
      schema={responseSchemas.HistoryResponse}
      historical
      suffix={'?' + query.toString()}
    >
      {(h) => (
        <>
          <div className="page-heading">
            <div>
              <h1>{h.title ?? h.id}</h1>
              <p>
                <code>{h.id}</code> · Manifest sequence {h.seq}
              </p>
            </div>
            <SemanticValue value={h.kind} known={historyKinds} />
          </div>
          <HistoricalWarning />
          <div className="detail-grid">
            <section className="panel detail-main record-main">
              <h2>Lineage and links</h2>
              <p className="scope-note">
                References carry opaque IDs. Links follow their backend relation
                type. A target may be absent from the chosen projection.
              </p>
              {Object.entries(h.links).length ? (
                <dl>
                  {Object.entries(h.links).map(([rel, targets]) => (
                    <div key={rel}>
                      <dt>
                        <SemanticValue
                          value={rel}
                          known={historyLinkRelations}
                        />
                      </dt>
                      <dd>
                        {targets.length
                          ? targets.map((target) => (
                              <p key={target}>
                                <HistoryLinkTarget
                                  relation={rel}
                                  target={target}
                                />
                              </p>
                            ))
                          : 'No targets supplied'}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p>No links supplied.</p>
              )}
              <h2>Annotations</h2>
              <p className="scope-note">
                At most 100 annotations per page. No history record is upgraded
                to current evidence by an annotation.
              </p>
              {h.annotations.length ? (
                h.annotations.map((a) => (
                  <article className="annotation-item" key={a.id}>
                    <h3>
                      <code>{a.id}</code>{' '}
                      <SemanticValue
                        value={a.rel}
                        known={annotationRelations}
                      />
                    </h3>
                    <p>{a.note ?? 'No note supplied'}</p>
                    <dl>
                      <dt>Object</dt>
                      <dd>
                        {a.object ? (
                          <HistoricalTarget target={a.object} />
                        ) : (
                          'Not supplied'
                        )}
                      </dd>
                      <dt>Decision</dt>
                      <dd>
                        {a.decision ? (
                          <EntityAnchor
                            entity={{ id: a.decision, kind: 'decision' }}
                          />
                        ) : (
                          'Not supplied'
                        )}
                      </dd>
                      <dt>Trust source</dt>
                      <dd>
                        <SemanticValue value={a.source} known={trustSources} />
                      </dd>
                      <dt>Recorded</dt>
                      <dd>
                        <time>{a.at}</time>
                      </dd>
                    </dl>
                  </article>
                ))
              ) : (
                <p>No annotations supplied on this page.</p>
              )}
              <Pager
                next={h.annotations_next_cursor}
                cursorKey="annotations_cursor"
                resetKey={h.id}
              />
            </section>
            <aside className="panel facts">
              <h2>Manifest entry</h2>
              <dl>
                <dt>Trust source</dt>
                <dd>
                  <SemanticValue value={h.source} known={trustSources} />
                </dd>
                <dt>Unit kind</dt>
                <dd>
                  <SemanticValue
                    value={h.unit_kind}
                    known={['epic', 'story', 'ticket']}
                  />
                </dd>
                <dt>Archived state</dt>
                <dd>
                  <SemanticValue value={h.state} known={workStates} />
                </dd>
                <dt>Parent</dt>
                <dd>
                  {h.parent ? (
                    <EntityAnchor entity={{ id: h.parent, kind: 'work' }} />
                  ) : (
                    'Not supplied'
                  )}
                </dd>
                <dt>Subject ID</dt>
                <dd>
                  <code>{h.subject ?? 'Not supplied'}</code>
                </dd>
                <dt>Relation</dt>
                <dd>
                  <SemanticValue value={h.rel} known={annotationRelations} />
                </dd>
                <dt>Recorded</dt>
                <dd>
                  <time>{h.at}</time>
                </dd>
                <dt>Content SHA-256</dt>
                <dd>
                  <code>{h.sha256}</code>
                </dd>
              </dl>
              <p className="muted">
                Trust and audit conclusions are supplied by AEW. The content
                hash is displayed without claiming client-side verification.
              </p>
            </aside>
          </div>
        </>
      )}
    </DetailView>
  );
}
