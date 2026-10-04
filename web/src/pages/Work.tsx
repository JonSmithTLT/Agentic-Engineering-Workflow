import { InvestigationWorkspace } from '../components/InvestigationWorkspace';
import { ComparisonEntry } from '../components/ComparisonEntry';
import { DetailView, Reasons } from '../components/ProjectionViews';
import { useState } from 'react';
import { useSearchParams, Link, useLocation } from 'react-router-dom';
import { useProjection, comparisonScope } from '../client/queries';
import {
  useCapability,
  CapabilityGate,
  PageSnapshot,
  ProjectionMetadata,
} from '../client/dashboard';
import { responseSchemas, id as identity } from '../api/schema';
import { ticketStates, parentStates } from '../api/vocabulary';
import { SemanticValue, LoadError } from '../components/States';
import { SafeContent } from '../components/Content';
import { EntityAnchor } from '../components/EntityAnchor';
import { WorkTable } from '../components/WorkTable';
import { SinceViewed } from '../components/SinceViewed';
import { CopyCli } from '../components/CopyCli';
import { WorkGraph } from '../components/WorkGraph';
import { workRoute } from './work-model';
export function WorkPage() {
  return (
    <InvestigationWorkspace
      collection="work"
      results={<WorkResultsPage />}
      detail={(id, visible) => (
        <WorkDetailPage recordId={id} displayed={visible} />
      )}
    />
  );
}
function WorkResultsPage() {
  const [params, setParams] = useSearchParams();
  const available = useCapability('work').available;
  const parent = params.get('parent') ?? '';
  const validParent = !parent || identity.safeParse(parent).success;
  const query = useProjection(
    workRoute(params),
    responseSchemas.WorkListResponse,
    'list',
    available && validParent,
  );
  const [previous, setPrevious] = useState<string[]>([]);
  const view = params.get('view') ?? 'table';
  const values = [...new Set([...ticketStates, ...parentStates])];
  const state = params.get('state') ?? '',
    kind = params.get('kind') ?? '';
  function change(key: string, value: string) {
    setPrevious([]);
    setParams((old) => {
      const next = new URLSearchParams(old);
      if (value) next.set(key, value);
      else next.delete(key);
      next.delete('cursor');
      return next;
    });
  }
  function page(cursor: string) {
    setParams((old) => {
      const next = new URLSearchParams(old);
      if (cursor) next.set('cursor', cursor);
      else next.delete('cursor');
      return next;
    });
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1 tabIndex={-1}>Work</h1>
          <p>Inspect active work and recent finished records.</p>
        </div>
      </div>
      <PageSnapshot queries={[query]} />
      <CapabilityGate name="work">
        <div className="filter-bar">
          <label>
            State
            <select
              aria-label="State filter"
              value={state}
              onChange={(e) => change('state', e.target.value)}
            >
              <option value="">Active + recent finished</option>
              {state && !values.includes(state as (typeof values)[number]) && (
                <option value={state}>{state}</option>
              )}
              {values.map((v) => (
                <option key={v} value={v}>
                  {v.replaceAll('_', ' ')}
                </option>
              ))}
            </select>
          </label>
          <label>
            Kind
            <select
              aria-label="Kind filter"
              value={kind}
              onChange={(e) => change('kind', e.target.value)}
            >
              <option value="">All kinds</option>
              {kind && !['epic', 'story', 'ticket'].includes(kind) && (
                <option value={kind}>{kind}</option>
              )}
              {['epic', 'story', 'ticket'].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            Direct parent
            <input
              aria-label="Parent filter"
              value={parent}
              placeholder="Parent ID"
              onChange={(e) => change('parent', e.target.value)}
            />
          </label>
          <label>
            View
            <select
              aria-label="Work view"
              value={view}
              onChange={(e) => {
                setParams((old) => {
                  const next = new URLSearchParams(old);
                  next.set('view', e.target.value);
                  return next;
                });
              }}
            >
              <option value="table">Table</option>
              <option value="tree">Hierarchy on this page</option>
              <option value="graph">Graph on this page</option>
            </select>
          </label>
        </div>
        <p className="scope-note">
          Unfiltered results include hot work and at most 20 recent archived
          records. Select DONE or CANCELLED to inspect older finished work.
          Hierarchy shows only this page; parent rollups come from AEW.
        </p>
        {!validParent ? (
          <p role="alert">Enter a path-safe parent ID.</p>
        ) : !query.data ? (
          query.isError ? (
            <LoadError
              message={query.error.message}
              retry={() => {
                void query.refetch();
              }}
            />
          ) : (
            <p role="status">Loading work…</p>
          )
        ) : (
          <>
            {params.get('selected') && !query.data.value.data.items.some(item => item.id === params.get('selected')) && (
              <p className="scope-note" role="status">
                Selected record <code>{params.get('selected')}</code> is outside this loaded results page or filter. Detail remains selected; this does not mean the record is unavailable.
              </p>
            )}
            <SinceViewed
              key={
                query.data.value.project_id +
                workRoute(params) +
                comparisonScope()
              }
              project={query.data.value.project_id}
              scope={'work:' + workRoute(params) + comparisonScope()}
              revision={query.data.value.control_revision}
              items={query.data.value.data.items}
            />
            <section className="panel">
              <div className="panel-heading">
                <h2>Work records</h2>
                <span>
                  {query.data.value.data.items.length} records on this page
                </span>
              </div>
              {view === 'graph' ? (
                <WorkGraph
                  key={workRoute(params)}
                  items={query.data.value.data.items}
                />
              ) : (
                <WorkTable
                  key={workRoute(params)}
                  items={query.data.value.data.items}
                  tree={view === 'tree'}
                />
              )}
              <div className="pagination">
                <button
                  disabled={!params.get('cursor')}
                  onClick={() => {
                    setPrevious([]);
                    page('');
                  }}
                >
                  First page
                </button>
                <button
                  disabled={!params.get('cursor')}
                  onClick={() => {
                    const next = [...previous];
                    page(next.pop() ?? '');
                    setPrevious(next);
                  }}
                >
                  Previous page
                </button>
                <button
                  disabled={!query.data.value.data.next_cursor}
                  onClick={() => {
                    setPrevious((old) => [...old, params.get('cursor') ?? '']);
                    page(query.data!.value.data.next_cursor!);
                  }}
                >
                  Next page
                </button>
                {query.isFetching && <span role="status">Checking…</span>}
              </div>
            </section>
            {query.isError && (
              <p className="preview-note" role="alert">
                {query.error.message}{' '}
                <button
                  onClick={() => {
                    setPrevious([]);
                    page('');
                  }}
                >
                  Reload from first page
                </button>
              </p>
            )}
            <ProjectionMetadata record={query.data} />
          </>
        )}
      </CapabilityGate>
    </>
  );
}
export function WorkDetailPage({
  recordId,
  displayed = true,
}: { recordId?: string; displayed?: boolean } = {}) {
  const location = useLocation();
  return (
    <DetailView
      name="work"
      title="Work"
      path="/work"
      schema={responseSchemas.WorkResponse}
      recordId={recordId}
      displayed={displayed}
      presentation="work-summary"
    >
      {(work) => (
        <>
          <div className="page-heading">
            <div>
              <SemanticValue
                value={work.kind}
                known={['epic', 'story', 'ticket']}
              />
              <h1 tabIndex={-1} data-work-heading={work.id}>{work.title}</h1>
              <ComparisonEntry work={work.id} />
              <CopyCli kind="work" id={work.id} />
            </div>
            <SemanticValue
              value={work.state}
              known={work.kind === 'ticket' ? ticketStates : parentStates}
            />
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
                <h2>Backend blockers and reasons</h2>
              </div>
              <h3>blocked_by</h3>
              <Reasons values={work.blocked_by} />
              <h3>reasons (record-level)</h3>
              <Reasons values={work.reasons} />
              <div className="panel-heading">
                <h2>Related records</h2>
              </div>
              {work.related.length ? (
                work.related.map((r, i) => (
                  <p key={i}>
                    <EntityAnchor entity={r} />
                  </p>
                ))
              ) : (
                <p className="muted">No related records supplied.</p>
              )}
              {!!work.children.length && (
                <>
                  <div className="panel-heading">
                    <h2>Direct children</h2>
                    <Link
                      to={(() => {
                        const params = new URLSearchParams(location.search);
                        for (const key of ['cursor', 'state', 'kind', 'view'])
                          params.delete(key);
                        params.set('parent', work.id);
                        params.set('work_pane', 'results');
                        return '/work?' + params.toString();
                      })()}
                    >
                      Inspect children
                    </Link>
                  </div>
                  {work.children.map((child) => (
                    <p key={child}>
                      <EntityAnchor entity={{ id: child, kind: 'work' }} />
                    </p>
                  ))}
                  {work.children_truncated && (
                    <p className="preview-note">
                      Child preview truncated. Use the parent filter, with
                      DONE/CANCELLED for older archived children.
                    </p>
                  )}
                </>
              )}
            </section>
            <aside className="panel facts">
              <h2>Backend projection</h2>
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
                <dt>Parent</dt>
                <dd>
                  {work.parent_id ? (
                    <EntityAnchor
                      entity={{ id: work.parent_id, kind: 'work' }}
                    />
                  ) : (
                    'None supplied'
                  )}
                </dd>
                <dt>Attention</dt>
                <dd>{work.has_attention ? 'Reported' : 'None reported'}</dd>
                <dt>Integration status</dt>
                <dd>
                  <SemanticValue
                    value={work.integration?.status ?? null}
                    known={['prepared', 'publishing', 'conflict', 'superseded']}
                  />
                </dd>
                <dt>Integrated commit</dt>
                <dd>
                  <code>{work.integration?.commit ?? 'Not supplied'}</code>
                </dd>
                <dt>Commit-ready sequence</dt>
                <dd>{work.integration?.commit_ready_seq ?? 'Not supplied'}</dd>
                <dt>Updated</dt>
                <dd>
                  <time>{work.updated_at}</time>
                </dd>
              </dl>
              {work.rollup && (
                <>
                  <h2>Subtree Tickets</h2>
                  <dl>
                    <dt>Open</dt>
                    <dd>{work.rollup.open}</dd>
                    <dt>Done</dt>
                    <dd>{work.rollup.done}</dd>
                    <dt>Cancelled</dt>
                    <dd>{work.rollup.cancelled}</dd>
                  </dl>
                </>
              )}
              <p className="muted">
                All counts and conclusions are supplied by AEW.
              </p>
            </aside>
          </div>
        </>
      )}
    </DetailView>
  );
}
