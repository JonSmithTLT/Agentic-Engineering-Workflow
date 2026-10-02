import {
  ticketStates,
  parentStates,
  workStates,
  invocationStatuses,
  invocationRoles,
} from '../vocabulary';
/** Provisional presentation adapter. Domain assumptions stay here until C0. */
import { Link, useParams } from 'react-router-dom';
import { useProjection } from '../../client/queries';
import { responseSchemas } from '../schema';
import { selectedWorld, worlds } from './worlds';
import {
  CapabilityWarnings,
  SnapshotBanner,
  SemanticValue,
  LoadError,
} from '../../components/States';
import { SafeContent } from '../../components/Content';
import { entityLink, detailRoute } from '../links';
function WorldPicker() {
  return (
    <label className="world-picker">
      Demo scenario
      <select
        value={selectedWorld().fixture}
        onChange={(e) => {
          const url = new URL(location.href);
          url.searchParams.set('fixture', e.target.value);
          location.assign(url);
        }}
      >
        {worlds.map((w) => (
          <option key={w.fixture} value={w.fixture}>
            {w.fixture} · {w.name}
          </option>
        ))}
      </select>
    </label>
  );
}
export function OverviewPreview() {
  const query = useProjection(
    '/overview',
    responseSchemas.OverviewResponse,
    'overview',
  );
  const record = query.data;
  const data = record?.value.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Overview</h1>
          <p>What AEW is doing, and what needs attention.</p>
        </div>
        <WorldPicker />
      </div>
      <SnapshotBanner
        checks={
          record
            ? [
                {
                  revision: record.value.control_revision,
                  failed: query.isError,
                },
              ]
            : []
        }
        initialFailure={query.isError}
      />
      {!data ? (
        query.isError ? (
          <LoadError
            message={query.error.message}
            retry={() => {
              void query.refetch();
            }}
          />
        ) : (
          <p role="status">Loading projection…</p>
        )
      ) : (
        <>
          <CapabilityWarnings values={data.capabilities} />
          <section className="briefing panel">
            <div>
              <span className="muted">Backend summary</span>
              <SafeContent {...data.summary} />
            </div>
            <div className="health">
              <span className="muted">Reported health</span>
              <SemanticValue
                value={data.health.status}
                known={['HEALTHY', 'DEGRADED', 'UNHEALTHY', 'UNKNOWN']}
              />
              {data.health.reasons.map((r) => (
                <p key={r.code}>
                  {r.code}: {r.message}
                </p>
              ))}
            </div>
          </section>
          <div className="overview-grid">
            <section className="panel">
              <div className="panel-heading">
                <h2>
                  Active work <span>{data.counts.work.open}</span>
                </h2>
                <Link to={'/work' + location.search}>Inspect work</Link>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Work</th>
                      <th>Kind</th>
                      <th>State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.work.map((w) => (
                      <tr key={w.id}>
                        <td>
                          <Link
                            to={detailRoute('work', w.id) + location.search}
                          >
                            {w.title}
                          </Link>
                        </td>
                        <td>
                          <SemanticValue
                            value={w.kind}
                            known={['epic', 'story', 'ticket']}
                          />
                        </td>
                        <td>
                          <SemanticValue
                            value={w.state}
                            known={
                              w.kind === 'ticket'
                                ? ticketStates
                                : parentStates
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!data.work.length && (
                <p className="empty">No active work reported.</p>
              )}
            </section>
            <section className="panel attention-panel">
              <div className="panel-heading">
                <h2>
                  Needs attention <span>{data.counts.attention}</span>
                </h2>
              </div>
              {data.attention.map((a) => (
                <article className="attention-item" key={a.id}>
                  <span className="attention-marker" aria-hidden="true">
                    !
                  </span>
                  <div>
                    <h3>{a.title}</h3>
                    <SafeContent {...a.summary} />
                    {entityLink(a.subject) && (
                      <Link to={entityLink(a.subject)! + location.search}>
                        {a.subject.title}
                      </Link>
                    )}
                  </div>
                </article>
              ))}
              {!data.attention.length && (
                <p className="empty">No attention items reported.</p>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>
                  Running now <span>{data.counts.runs}</span>
                </h2>
              </div>
              {data.runs.map((r) => (
                <article className="run-item" key={r.id}>
                  <div>
                    <h3>{r.work.title}</h3>
                    <p>
                      <SemanticValue
                        value={r.role}
                        known={invocationRoles}
                      />
                    </p>
                  </div>
                  <SemanticValue
                    value={r.status}
                    known={invocationStatuses}
                  />
                </article>
              ))}
              {!data.runs.length && (
                <p className="empty">No active runs reported.</p>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>Recent activity</h2>
              </div>
              {data.activity.map((a) => (
                <article className="activity-item" key={a.id}>
                  <time>
                    {new Date(a.occurred_at).toLocaleTimeString()}
                  </time>
                  <div>
                    <h3>{a.title}</h3>
                    <p>{a.subject.title}</p>
                  </div>
                </article>
              ))}
            </section>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <h2>Recently finished work</h2>
              <span>At most 20 records</span>
            </div>
            <p className="muted">
              Archived records are historical references, never current
              evidence.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Work</th>
                    <th>State</th>
                    <th>Record</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((w) => (
                    <tr key={w.id}>
                      <td>
                        <Link
                          to={detailRoute('work', w.id) + location.search}
                        >
                          {w.title}
                        </Link>
                      </td>
                      <td>
                        <SemanticValue value={w.state} known={workStates} />
                      </td>
                      <td>{w.archived ? 'Archived' : 'Hot'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="projection-meta">
            <span>
              Revision <code>{record.value.control_revision}</code>
            </span>
            <span>
              Generated <time>{record.value.generated_at}</time>
            </span>
            <span>
              Last checked <time>{record.last_checked_at}</time>
            </span>
          </div>
        </>
      )}
    </>
  );
}
export function TicketPreview() {
  const { id } = useParams();
  const world = selectedWorld();
  const payload = world.responses[`/work/${id}`];
  const parsed = responseSchemas.WorkResponse.safeParse(payload);
  const work = parsed.success ? parsed.data.data : undefined;
  if (!work)
    return (
      <div className="empty">
        <h1>Work preview unavailable</h1>
        <p>This scenario does not include that detail.</p>
        <Link to={'/' + location.search}>Return to Overview</Link>
      </div>
    );
  return (
    <>
      <div className="breadcrumb">
        <Link to={'/' + location.search}>Overview</Link>
        <span>/</span>
        <span>Work preview</span>
      </div>
      <div className="page-heading">
        <div>
          <span className="muted">
            <SemanticValue
              value={work.kind}
              known={['epic', 'story', 'ticket']}
            />{' '}
            · {work.id}
          </span>
          <h1>{work.title}</h1>
        </div>
        <SemanticValue value={work.state} known={workStates} />
      </div>
      <div className="preview-note" role="note">
        Provisional Ticket detail. Demo data; pending C0 contract approval.
      </div>
      {work.archived && (
        <p className="preview-note" role="note">
          Archived work. Historical reference; never current evidence.
        </p>
      )}
      <div className="detail-grid">
        <section className="panel detail-main">
          <div className="panel-heading">
            <h2>Intent and context</h2>
          </div>
          <SafeContent {...work.summary} />
          <div className="panel-heading">
            <h2>Linked evidence</h2>
          </div>
          {work.related.map((r) => (
            <p key={r.id}>
              {entityLink(r) ? (
                <Link to={entityLink(r)! + location.search}>{r.title}</Link>
              ) : (
                r.title
              )}
            </p>
          ))}
          <div className="panel-heading">
            <h2>Backend reasons</h2>
          </div>
          {work.blocked_by.map((r, i) => (
            <p key={i}>{r.message ?? r.code}</p>
          ))}
          {work.reasons.length ? (
            work.reasons.map((r) => (
              <p key={r.code}>
                <strong>{r.code}</strong> {r.message}
              </p>
            ))
          ) : (
            <p className="muted">No additional reasons supplied.</p>
          )}
        </section>
        <aside className="panel facts">
          <h2>Projection fields</h2>
          <dl>
            <dt>Risk class</dt>
            <dd>{work.risk_class ?? 'Not supplied'}</dd>
            <dt>Plan revision</dt>
            <dd>{work.plan_revision ?? 'Not supplied'}</dd>
            <dt>Mutating</dt>
            <dd>
              {work.mutating === null
                ? 'Not applicable'
                : work.mutating
                  ? 'Yes'
                  : 'No'}
            </dd>
            <dt>Archived</dt>
            <dd>{work.archived ? 'Yes' : 'No'}</dd>
            <dt>Integration status</dt>
            <dd>
              <SemanticValue
                value={work.integration?.status ?? null}
                known={['prepared', 'publishing', 'conflict', 'superseded']}
              />
            </dd>
            <dt>Last updated</dt>
            <dd>{work.updated_at}</dd>
            <dt>Attention</dt>
            <dd>{work.has_attention ? 'Reported' : 'None reported'}</dd>
          </dl>
          <p className="muted">
            These are backend-reported values. The dashboard does not
            determine gate legality.
          </p>
        </aside>
      </div>
    </>
  );
}
