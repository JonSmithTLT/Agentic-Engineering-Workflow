import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useDashboard } from '../../../client/dashboard';
import { useProjection, useReadSession } from '../../../client/queries';
import { ReadTransport, accessRefused } from '../../transport';
import { RequestLog } from '../../diagnostics';
import { readClock } from '../../../client/clock';
import { investigationContract } from './registration';
import { investigationSchemas, sourceBindingIssue, type ComparisonSource } from './schema';
const policy = { base: '/api/preview/investigation/v0.1', routes: /^\/(?:sources|packets)(?:[/?]|$)/ };
export function useInvestigationReader(owner: string, name: string, snapshot = 'chooser', visibility = 'unresolved') {
  const base = useReadSession(), project = useDashboard().project.data?.value.project_id, client = useQueryClient();
  const reader = useMemo(() => {
    const r = new ReadTransport(undefined, () => readClock.now(), new RequestLog(), policy);
    r.reset({ ...base.identity, dataset: `${base.identity.dataset}:investigation:${name}:${owner}:${visibility}`, contract: `provisional:0.1.0:${investigationContract.sha256}`, snapshot });
    if (project) r.context.bind(project);
    return r;
  }, [base, project, owner, name, snapshot, visibility]);
  useEffect(() => () => {
    reader.context.retire();
    const key = reader.context.key('/sources');
    const predicate = (q: { queryKey: readonly unknown[] }) => q.queryKey[1] === key;
    void client.cancelQueries({ predicate }); client.removeQueries({ predicate });
  }, [reader, client]);
  useEffect(() => {
    let clearing = false;
    return client.getQueryCache().subscribe(event => {
      if (clearing || !('query' in event) || event.query.queryKey[1] !== reader.context.key('/sources') || !accessRefused(event.query.state.error)) return;
      clearing = true;
      reader.clearRepresentations();
      for (const query of client.getQueryCache().findAll({ predicate: q => q.queryKey[1] === reader.context.key('/sources') })) {
        if (query.state.data !== undefined) query.setState({ data: undefined, error: event.query.state.error });
      }
      clearing = false;
    });
  }, [reader, client]);
  return { reader, ready: !!project };
}
/** Discover identity once, discard that payload, then read in an exact bound context. */
export function useComparisonSource(owner: string, name: string, sourceId: string, displayed: boolean, initialize = false) {
  const discovery = useInvestigationReader(`${owner}:identity:${sourceId}`, name);
  const [identity, setAnchor] = useState<(Pick<ComparisonSource, 'mode' | 'snapshot_id' | 'visibility_scope'> & { sourceId: string }) | null>(null);
  const anchor = identity?.sourceId === sourceId ? identity : null;
  const [failed, setFailure] = useState<{ sourceId: string; error: Error } | null>(null), [retry, setRetry] = useState(0);
  const failure = failed?.sourceId === sourceId ? failed.error : null;
  const [initialized, setInitialized] = useState('');
  const route = `/sources/${encodeURIComponent(sourceId)}?case=${encodeURIComponent(name)}`;
  useEffect(() => {
    if (!discovery.ready || !sourceId || anchor || (!displayed && !initialize)) return;
    const controller = new AbortController();
    discovery.reader.get(route, investigationSchemas.ComparisonSourceResponse, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      const source = result.value.data, issue = sourceBindingIssue(source);
      if (source.id !== sourceId || issue) throw new Error(issue ?? 'Source identity mismatch');
      setAnchor({ sourceId, mode: source.mode, snapshot_id: source.snapshot_id, visibility_scope: source.visibility_scope }); setFailure(null);
      discovery.reader.reset(discovery.reader.context.identity, false); discovery.reader.context.retire();
    }).catch(error => { if (!controller.signal.aborted) setFailure({ sourceId, error }); });
    return () => controller.abort();
  }, [discovery.ready, discovery.reader, sourceId, route, anchor, displayed, initialize, retry]);
  const bound = useInvestigationReader(`${owner}:${sourceId}`, name, anchor?.snapshot_id ?? (anchor ? 'current' : 'unbound'), anchor?.visibility_scope);
  const schema = useMemo(() => investigationSchemas.ComparisonSourceResponse.superRefine((value, ctx) => {
    const s = value.data, issue = sourceBindingIssue(s) ?? (s.id !== sourceId || s.mode !== anchor?.mode || s.snapshot_id !== anchor?.snapshot_id || s.visibility_scope !== anchor?.visibility_scope ? 'Source snapshot/visibility binding mismatch' : undefined);
    if (issue) ctx.addIssue({ code: 'custom', message: issue });
  }), [sourceId, anchor]);
  const query = useProjection(route, schema, displayed && anchor?.mode === 'CURRENT' ? 'detail' : 'history', !!sourceId && !!anchor && bound.ready, displayed || (initialize && initialized !== sourceId), bound.reader);
  useEffect(() => { if (query.data) setInitialized(sourceId); }, [query.data, sourceId]);
  const value = query.data?.value.data;
  const issue = value && (sourceBindingIssue(value) ?? (value.id !== sourceId || value.mode !== anchor?.mode || value.snapshot_id !== anchor?.snapshot_id || value.visibility_scope !== anchor?.visibility_scope ? 'Source snapshot/visibility binding mismatch' : undefined));
  return { ...query, data: issue ? undefined : query.data, error: issue ? new Error(issue) : query.error ?? failure, reader: bound.reader, refetch: () => anchor ? query.refetch() : (setFailure(null), setRetry(n => n + 1)), pending: !!sourceId && !query.data && !query.error && !failure && !issue };
}
