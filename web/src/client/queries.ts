import { readClock } from './clock';
import { QueryClient, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, useSyncExternalStore } from 'react';
import type { z } from 'zod';
import { accessRefused, transport } from '../api/transport';
import { installRevisionReconciliation } from './revisions';
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: 0,
    },
  },
});
export const pollIntervals = {
  overview: 2000,
  list: 5000,
  detail: 10000,
  history: false,
} as const;
export function comparisonScope() {
  const identity = transport.context.identity;
  return JSON.stringify([
    identity.mode,
    identity.dataset,
    identity.snapshot,
    identity.authorization_generation,
  ]);
}
export function projectionKey(route: string, reader = transport) {
  return ['projection', reader.context.key(route), route] as const;
}
export function useReadSession() {
  useSyncExternalStore(transport.subscribe, transport.snapshot);
  return transport.context;
}
export async function resetReadSession(identity = transport.context.identity) {
  transport.context.retire();
  await queryClient.cancelQueries();
  queryClient.removeQueries();
  transport.reset(identity);
}
export function installVisibility(
  client: QueryClient,
  doc: Document = document,
) {
  const onVisible = () => {
    if (doc.visibilityState === 'visible' && !readClock.manual)
      void client.refetchQueries({ type: 'active' });
  };
  doc.addEventListener('visibilitychange', onVisible);
  const disposeReconciliation = installRevisionReconciliation(client, doc);
  const onFocus = () => {
    if (doc.visibilityState === 'visible' && !readClock.manual)
      void client.refetchQueries({ type: 'active' });
  };
  window.addEventListener('focus', onFocus);
  return () => {
    disposeReconciliation();
    doc.removeEventListener('visibilitychange', onVisible);
    window.removeEventListener('focus', onFocus);
  };
}
export function useProjection<T>(
  route: string,
  schema: z.ZodType<T>,
  kind: keyof typeof pollIntervals,
  available = true,
  displayed = true,
  reader = transport,
) {
  useReadSession();
  const localClient = useQueryClient();
  const [visible, setVisible] = useState(readClock.visible());
  useEffect(() => {
    const change = () => setVisible(readClock.visible());
    return readClock.subscribe(change);
  }, []);
  const query = useQuery({
    queryKey: projectionKey(route, reader),
    queryFn: ({ signal }) => reader.get(route, schema, signal),
    enabled: available && displayed,
    refetchInterval:
      visible && displayed && !readClock.manual ? pollIntervals[kind] : false,
    refetchIntervalInBackground: false,
  });
  useEffect(() => {
    if (accessRefused(query.error))
      localClient
        .getQueryCache()
        .find({ queryKey: projectionKey(route, reader), exact: true })
        ?.setState({ data: undefined });
  }, [query.error, route, localClient, reader]);
  return accessRefused(query.error) ? { ...query, data: undefined } : query;
}
