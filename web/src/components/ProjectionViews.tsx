import { useState, type ReactNode } from 'react';
import {
  Link,
  useLocation,
  useSearchParams,
  useParams,
} from 'react-router-dom';
import type { z } from 'zod';
import type { Projection } from '../api/transport';
import { useProjection, comparisonScope } from '../client/queries';
import {
  CapabilityGate,
  PageSnapshot,
  ProjectionMetadata,
  useCapability,
} from '../client/dashboard';
import { id as identity } from '../api/schema';
import { LoadError } from './States';
import { SinceViewed } from './SinceViewed';
import { CopyCli } from './CopyCli';
import { EntityAnchor } from './EntityAnchor';

function locationScope() {
  return comparisonScope();
}
type Envelope<T> = {
  schema_version: '0.1.2';
  project_id: string;
  control_revision: string;
  generated_at: string;
  data: T;
};
type List<T> = { items: T[]; next_cursor: string | null };
export function listRoute(
  path: string,
  params: URLSearchParams,
  filters: readonly string[] = [],
) {
  const query = new URLSearchParams({ limit: '100' });
  for (const key of [...filters, 'cursor']) {
    const value = params.get(key);
    if (value) query.set(key, value);
  }
  return `${path}?${query}`;
}
export function Pager({
  next,
  cursorKey = 'cursor',
  resetKey = '',
  children,
}: {
  next: string | null;
  cursorKey?: string;
  resetKey?: string;
  children?: ReactNode;
}) {
  const [params, setParams] = useSearchParams();
  const [history, setHistory] = useState<{ scope: string; values: string[] }>({
    scope: resetKey,
    values: [],
  });
  const previous = history.scope === resetKey ? history.values : [];
  const current = params.get(cursorKey) ?? '';
  function page(value: string, values: string[]) {
    setHistory({ scope: resetKey, values });
    setParams((old) => {
      const p = new URLSearchParams(old);
      if (value) p.set(cursorKey, value);
      else p.delete(cursorKey);
      return p;
    });
  }
  return (
    <div className="pagination">
      <button disabled={!current} onClick={() => page('', [])}>
        First page
      </button>
      <button
        disabled={!current}
        onClick={() => page(previous.at(-1) ?? '', previous.slice(0, -1))}
      >
        Previous page
      </button>
      <button
        disabled={!next}
        onClick={() => page(next!, [...previous, current])}
      >
        Next page
      </button>
      {children}
    </div>
  );
}
export function CollectionView<T>({
  name,
  title,
  description,
  path,
  schema,
  historical = false,
  filters = [],
  filterUI,
  valid = true,
  children,
}: {
  name: string;
  title: string;
  description: string;
  path: string;
  schema: z.ZodType<Envelope<List<T>>>;
  historical?: boolean;
  filters?: readonly string[];
  filterUI?: ReactNode;
  valid?: boolean;
  children: (items: T[]) => ReactNode;
}) {
  const [params] = useSearchParams();
  const available = useCapability(name).available;
  const route = listRoute(path, params, filters);
  const query = useProjection(
    route,
    schema,
    historical ? 'history' : 'list',
    available && valid,
  );
  const scope = new URLSearchParams(params);
  scope.delete('cursor');
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
      </div>
      <PageSnapshot queries={[query]} />
      <CapabilityGate name={name}>
        {filterUI}
        {!valid ? (
          <p role="alert">Check the filter values. No request was sent.</p>
        ) : !query.data ? (
          query.isError ? (
            <LoadError
              message={query.error.message}
              retry={() => {
                void query.refetch();
              }}
            />
          ) : (
            <p role="status">Loading records…</p>
          )
        ) : (
          <>
            {name === 'runs' && (
              <SinceViewed
                key={query.data.value.project_id + route + locationScope()}
                project={query.data.value.project_id}
                scope={'runs:' + route + locationScope()}
                revision={query.data.value.control_revision}
                items={(
                  query.data.value.data.items as {
                    id: string;
                    status?: string | null;
                  }[]
                ).map((item) => ({ id: item.id, state: item.status ?? null }))}
              />
            )}
            <section className="panel collection-panel">
              <div className="panel-heading">
                <h2>{title} records</h2>
                <span>
                  {query.data.value.data.items.length} records on this page
                </span>
              </div>
              {query.data.value.data.items.length ? (
                children(query.data.value.data.items)
              ) : (
                <p className="empty">No records in this scope.</p>
              )}
              <Pager
                next={query.data.value.data.next_cursor}
                resetKey={scope.toString()}
              >
                <button
                  onClick={() => {
                    void query.refetch();
                  }}
                >
                  Refresh page
                </button>
                {query.isFetching && <span role="status">Checking…</span>}
              </Pager>
            </section>
            {query.isError && (
              <LoadError
                message={query.error.message}
                retry={() => {
                  void query.refetch();
                }}
              />
            )}
            <ProjectionMetadata record={query.data} />
          </>
        )}
      </CapabilityGate>
    </>
  );
}
export function DetailView<T>({
  name,
  title,
  path,
  schema,
  historical = false,
  suffix = '',
  children,
}: {
  name: string;
  title: string;
  path: string;
  schema: z.ZodType<Envelope<T>>;
  historical?: boolean;
  suffix?: string;
  children: (data: T, projection: Projection<Envelope<T>>) => ReactNode;
}) {
  const { id = '' } = useParams();
  const location = useLocation();
  const available = useCapability(name).available;
  const valid = identity.safeParse(id).success;
  const query = useProjection(
    `${path}/${encodeURIComponent(id)}${suffix}`,
    schema,
    historical ? 'history' : 'detail',
    available && valid,
  );
  return (
    <>
      <div className="breadcrumb">
        <Link to={path + location.search}>{title}</Link>
        <span>/</span>
        <code>{id}</code>
      </div>
      <PageSnapshot queries={[query]} />
      <CapabilityGate name={name}>
        {!valid ? (
          <p role="alert">Invalid record ID.</p>
        ) : !query.data ? (
          query.isError ? (
            <LoadError
              message={query.error.message}
              retry={() => {
                void query.refetch();
              }}
            />
          ) : (
            <p role="status">Loading record…</p>
          )
        ) : (
          <>
            <div className="entity-actions">
              <CopyCli kind={name === 'runs' ? 'invocation' : name} id={id} />
              {name === 'evidence' && (
                <p className="scope-note">
                  This AEW CLI has no read-only evidence show command.
                </p>
              )}
            </div>
            {children(query.data.value.data, query.data)}
            {historical && (
              <button
                onClick={() => {
                  void query.refetch();
                }}
              >
                Refresh record
              </button>
            )}
            {query.isError && (
              <LoadError
                message={query.error.message}
                retry={() => {
                  void query.refetch();
                }}
              />
            )}
            <ProjectionMetadata record={query.data} />
          </>
        )}
      </CapabilityGate>
    </>
  );
}
export function Reasons({
  values,
}: {
  values: { code: string; message: string | null }[];
}) {
  return values.length ? (
    <ul className="reason-list">
      {values.map((r, i) => (
        <li key={i}>
          <span>{r.message ?? 'No explanation supplied'}</span>{' '}
          <code>{r.code}</code>
        </li>
      ))}
    </ul>
  ) : (
    <p className="muted">No reasons supplied.</p>
  );
}
export function References({
  values,
}: {
  values: { id: string; kind: string; title: string | null }[];
}) {
  return values.length ? (
    <ul className="reference-list">
      {values.map((r, i) => (
        <li key={i}>
          <code>{r.id}</code> <EntityAnchor entity={r} />
        </li>
      ))}
    </ul>
  ) : (
    <p className="muted">No references supplied.</p>
  );
}
