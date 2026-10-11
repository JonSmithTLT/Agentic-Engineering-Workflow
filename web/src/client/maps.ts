import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { z } from 'zod';
import { transport } from '../api/transport';
import { projectionKey, useProjection } from './queries';

/** Only the displayed Maps activity owns its body and validator. */
export function useMapRead<T>(route: string, schema: z.ZodType<T>, enabled: boolean, summary = false) {
  const client = useQueryClient();
  const context = transport.context;
  const query = useProjection(route, schema, summary ? 'maps' : 'history', enabled, enabled, transport, summary);
  useEffect(() => {
    if (!enabled) return;
    const key = projectionKey(route);
    return () => {
      void client.cancelQueries({ queryKey: key, exact: true });
      client.removeQueries({ queryKey: key, exact: true });
      if (transport.context === context) transport.forget(route);
    };
  }, [client, context, route, enabled]);
  return query;
}
