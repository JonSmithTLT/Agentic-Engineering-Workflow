import { reconciliationGroup } from '../api/read-context';
import { readClock } from './clock';
import type { QueryClient } from '@tanstack/react-query';
import type { Projection } from '../api/transport';
type RevisionEnvelope = { project_id: string; control_revision: string };
function revision(data: unknown) {
  const value = (data as Projection<RevisionEnvelope> | undefined)?.value;
  if (
    !value ||
    typeof value.project_id !== 'string' ||
    typeof value.control_revision !== 'string' ||
    !/^(0|[1-9][0-9]*)$/.test(value.control_revision)
  )
    return undefined;
  return { project: value.project_id, number: BigInt(value.control_revision) };
}
/** Catch active visible projections up to observed revisions, without retry loops. */
export function installRevisionReconciliation(
  client: QueryClient,
  doc: Document = document,
) {
  const attempted = new WeakMap<object, bigint>();
  let disposed = false;
  function reconcile() {
    if (disposed || readClock.manual || doc.visibilityState !== 'visible')
      return;
    const active = client
      .getQueryCache()
      .findAll({ type: 'active', queryKey: ['projection'] });
    const records = active.flatMap((query) => {
      const current = revision(query.state.data);
      return current ? [{ query, ...current }] : [];
    });
    const highest = new Map<string, bigint>();
    for (const record of records) {
      const prior = highest.get(
        reconciliationGroup(record.query.queryKey[1], record.project),
      );
      if (prior === undefined || record.number > prior)
        highest.set(
          reconciliationGroup(record.query.queryKey[1], record.project),
          record.number,
        );
    }
    for (const { query, project, number } of records) {
      const target = highest.get(
        reconciliationGroup(query.queryKey[1], project),
      )!;
      if (
        number >= target ||
        query.state.fetchStatus !== 'idle' ||
        attempted.get(query) === target
      )
        continue;
      // One immediate attempt per observed target. A stuck/304 projection keeps
      // its old revision and warning; its configured refresh policy still applies.
      attempted.set(query, target);
      void client.refetchQueries(
        { queryKey: query.queryKey, exact: true, type: 'active' },
        { cancelRefetch: false },
      );
    }
  }
  const unsubscribe = client.getQueryCache().subscribe((event) => {
    if (
      (event.type === 'updated' && event.action.type === 'success') ||
      event.type === 'observerAdded' ||
      event.type === 'observerOptionsUpdated'
    )
      reconcile();
  });
  doc.addEventListener('visibilitychange', reconcile);
  reconcile();
  return () => {
    disposed = true;
    unsubscribe();
    doc.removeEventListener('visibilitychange', reconcile);
  };
}
