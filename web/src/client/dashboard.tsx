import { RecordInspection } from '../components/Investigation';
import { createContext, useContext, type ReactNode } from 'react';
import { useProjection } from './queries';
import { responseSchemas } from '../api/schema';
import { capabilityView } from '../api/capabilities';
import type { Projection } from '../api/transport';
import { SnapshotBanner, LoadError, Unavailable } from '../components/States';
function useDashboardState() {
  const project = useProjection(
    '/project',
    responseSchemas.ProjectResponse,
    'detail',
  );
  const capabilities = useProjection(
    '/capabilities',
    responseSchemas.CapabilitiesResponse,
    'list',
    !!project.data,
  );
  const caps = capabilities.data?.value.data;
  const overviewAvailable = capabilityView(caps?.overview).available;
  const overview = useProjection(
    '/overview',
    responseSchemas.OverviewResponse,
    'overview',
    overviewAvailable,
  );
  return {
    capabilities,
    project,
    overview,
    caps,
    common: [capabilities, project, ...(overviewAvailable ? [overview] : [])],
  };
}
const DashboardContext = createContext<ReturnType<
  typeof useDashboardState
> | null>(null);
export function DashboardProvider({ children }: { children: ReactNode }) {
  const state = useDashboardState();
  return (
    <DashboardContext.Provider value={state}>
      {children}
    </DashboardContext.Provider>
  );
}
export function useDashboard() {
  const value = useContext(DashboardContext);
  if (!value) throw new Error('Dashboard provider missing');
  return value;
}
export function useCapability(name: string) {
  return capabilityView(useDashboard().caps?.[name]);
}
export type ProjectionQuery = {
  isEnabled?: boolean;
  data?: Projection<{ control_revision: string; generated_at: string }>;
  isError: boolean;
  error: Error | null;
};
export function PageSnapshot({
  queries = [],
}: {
  queries?: ProjectionQuery[];
}) {
  const visibleQueries = queries.filter((q) => q.isEnabled !== false);
  const all = [...useDashboard().common, ...visibleQueries].filter(
    (q) => q.isEnabled !== false,
  );
  return (
    <SnapshotBanner
      checks={
        visibleQueries.some((q) => q.isError && !q.data)
          ? []
          : all.flatMap((q) =>
              q.data
                ? [
                    {
                      revision: q.data.value.control_revision,
                      failed: q.isError,
                    },
                  ]
                : [],
            )
      }
      initialFailure={all.some((q) => q.isError && !q.data)}
    />
  );
}
export function CapabilityGate({
  name,
  children,
}: {
  name: string;
  children: ReactNode;
}) {
  const { capabilities, caps, project } = useDashboard();
  const value = useCapability(name);
  if (!project.data && project.isError)
    return (
      <LoadError
        message={project.error.message}
        retry={() => {
          void project.refetch();
        }}
      />
    );
  if (!caps)
    return capabilities.isError ? (
      <LoadError
        message={capabilities.error.message}
        retry={() => {
          void capabilities.refetch();
        }}
      />
    ) : (
      <p role="status">Loading project capabilities…</p>
    );
  if (!value.available)
    return (
      <>
        <Unavailable explanation={value.explanation} />
        {capabilities.data && caps[name] && (
          <RecordInspection
            kind="capability"
            record={caps[name]}
            source={capabilities.data}
            fallbackId={name}
          />
        )}
      </>
    );
  return <>{children}</>;
}
export function ProjectionMetadata({
  record,
}: {
  record: Projection<{ control_revision: string; generated_at: string }>;
}) {
  return (
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
  );
}
