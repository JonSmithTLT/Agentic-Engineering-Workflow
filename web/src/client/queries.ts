import { QueryClient, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { z } from 'zod';
import { transport } from '../api/transport';
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
export function installVisibility(
  client: QueryClient,
  doc: Document = document,
) {
  const onVisible = () => {
    if (doc.visibilityState === 'visible')
      void client.refetchQueries({ type: 'active' });
  };
  doc.addEventListener('visibilitychange', onVisible);
  const onFocus = () => {
    if (doc.visibilityState === 'visible')
      void client.refetchQueries({ type: 'active' });
  };
  window.addEventListener('focus', onFocus);
  return () => {
    doc.removeEventListener('visibilitychange', onVisible);
    window.removeEventListener('focus', onFocus);
  };
}
export function useProjection<T>(
  route: string,
  schema: z.ZodType<T>,
  kind: keyof typeof pollIntervals,
  available = true,
) {
  const [visible, setVisible] = useState(
    document.visibilityState === 'visible',
  );
  useEffect(() => {
    const change = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', change);
    return () => document.removeEventListener('visibilitychange', change);
  }, []);
  return useQuery({
    queryKey: ['projection', route],
    queryFn: ({ signal }) => transport.get(route, schema, signal),
    enabled: available,
    refetchInterval: visible ? pollIntervals[kind] : false,
    refetchIntervalInBackground: false,
  });
}
