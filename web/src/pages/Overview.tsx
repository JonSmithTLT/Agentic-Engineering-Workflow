import { Link, useLocation } from 'react-router-dom';
import {
  ticketStates,
  parentStates,
  workStates,
  invocationStatuses,
  invocationRoles,
} from '../api/vocabulary';
import {
  useDashboard,
  PageSnapshot,
  CapabilityGate,
  ProjectionMetadata,
} from '../client/dashboard';
import { SemanticValue, LoadError } from '../components/States';
import { SafeContent } from '../components/Content';
import { entityLink, detailRoute } from '../api/links';
export function OverviewPage() {
  const routeLocation = useLocation();
  const { overview: query } = useDashboard();
  const record = query.data;
  const data = record?.value.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Overview</h1>
          <p>What AEW is doing, and what needs attention.</p>
        </div>
      </div>
      <PageSnapshot queries={[query]} />
      <CapabilityGate name="overview">
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
                  <Link to={'/work' + routeLocation.search}>
                    Inspect work
                  </Link>
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
                              to={
                                detailRoute('work', w.id) +
                                routeLocation.search
                              }
                            >
                              <code className="work-record-id">{w.id}</code>{' '}
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
                        <Link
                          to={entityLink(a.subject)! + routeLocation.search}
                        >
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
                            to={
                              detailRoute('work', w.id) +
                              routeLocation.search
                            }
                          >
                            <code className="work-record-id">{w.id}</code>{' '}
                              {w.title}
                          </Link>
                        </td>
                        <td>
                          <SemanticValue
                            value={w.state}
                            known={workStates}
                          />
                        </td>
                        <td>{w.archived ? 'Archived' : 'Hot'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <ProjectionMetadata record={record} />
          </>
        )}
      </CapabilityGate>
    </>
  );
}
