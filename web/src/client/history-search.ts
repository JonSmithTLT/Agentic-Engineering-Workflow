import { useEffect, useSyncExternalStore } from 'react';
import { QueryClient } from '@tanstack/react-query';
import type { HistorySearchResponse } from '../api/additive-schema';
import type { SubmittedHistorySearch } from '../api/maps-history';
import { accessRefused, transport, type ReadTransport, type Projection } from '../api/transport';
import { projectionKey, queryClient, useReadSession } from './queries';

export type SearchDraft = { terms: string[]; kinds: string[]; since: string; until: string; limit: number };
export const emptySearchDraft = (): SearchDraft => ({ terms: [''], kinds: [], since: '', until: '', limit: 10 });
type SearchState = {
  draft: SearchDraft;
  submitted?: SubmittedHistorySearch;
  result?: Projection<HistorySearchResponse>;
  error?: string;
  pending: boolean;
};

/** One ephemeral operator search. Only submit can execute its query. */
export class HistorySearchSession {
  private state: SearchState = { draft: emptySearchDraft(), pending: false };
  private listeners = new Set<() => void>();
  private route?: string;
  private sequence = 0;
  private scope?: string;
  private permitted = false;
  constructor(private reader: ReadTransport, private client: QueryClient) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private change(next: SearchState) {
    this.state = next;
    this.listeners.forEach(listener => listener());
  }
  private discard() {
    this.sequence++;
    if (this.route) {
      void this.client.cancelQueries({ queryKey: projectionKey(this.route, this.reader), exact: true });
      this.client.removeQueries({ queryKey: projectionKey(this.route, this.reader), exact: true });
      this.reader.forget(this.route);
    }
    this.route = undefined;
  }
  bind(permitted: boolean) {
    const scope = this.reader.context.key('/history/search');
    if (scope !== this.scope || (!permitted && this.permitted)) {
      this.discard();
      this.scope = scope;
      this.change({ draft: emptySearchDraft(), pending: false });
    }
    this.permitted = permitted && !!this.reader.context.projectId && !this.reader.context.retired;
  }
  edit(draft: SearchDraft) { this.change({ ...this.state, draft }); }
  clear() {
    this.discard();
    this.change({ draft: emptySearchDraft(), pending: false });
  }
  suspend() {
    if (!this.state.pending) return;
    this.sequence++;
    if (this.route) void this.client.cancelQueries({ queryKey: projectionKey(this.route, this.reader), exact: true });
    this.change({ ...this.state, pending: false });
  }
  async submit(query: SubmittedHistorySearch) {
    if (!this.permitted || this.state.pending) return;
    let sequence = ++this.sequence;
    const context = this.reader.context;
    this.change({ ...this.state, error: undefined, pending: true });
    try {
      const [{ historySearchRoute }, { HistorySearchResponse }] = await Promise.all([
        import('../api/maps-history'), import('../api/additive-schema'),
      ]);
      if (sequence !== this.sequence || context !== this.reader.context || !this.permitted) return;
      const route = historySearchRoute(query);
      const same = route === this.route;
      if (!same) { this.discard(); sequence = this.sequence; }
      this.route = route;
      this.change({ ...this.state, submitted: query, result: same ? this.state.result : undefined });
      const expectedKinds = [...new Set(query.kinds ?? [])].sort();
      const schema = HistorySearchResponse.refine(value =>
        JSON.stringify(value.data.query.terms) === JSON.stringify(query.terms) &&
        JSON.stringify(value.data.query.kinds) === JSON.stringify(expectedKinds) &&
        value.data.query.since === (query.since ?? null) &&
        value.data.query.until === (query.until ?? null) &&
        value.data.query.limit === (query.limit ?? 10), 'Search response belongs to a different submitted query');
      const result = await this.client.fetchQuery({
        queryKey: projectionKey(route, this.reader),
        meta: { automaticRevalidation: false },
        staleTime: 0,
        retry: false,
        queryFn: ({ signal }) => this.reader.get(route, schema, signal),
      });
      if (sequence !== this.sequence || context !== this.reader.context || !this.permitted) return;
      this.change({ ...this.state, result, pending: false });
    } catch (error) {
      if (sequence !== this.sequence || context !== this.reader.context) return;
      const refused = accessRefused(error);
      if (refused && this.route) {
        this.client.removeQueries({ queryKey: projectionKey(this.route, this.reader), exact: true });
        this.reader.forget(this.route);
      }
      this.change({ ...this.state, result: refused ? undefined : this.state.result, pending: false,
        error: error instanceof Error ? error.message : 'Search failed' });
    }
  }
}

export const historySearchSession = new HistorySearchSession(transport, queryClient);
export function useHistorySearch(permitted: boolean) {
  const context = useReadSession();
  const state = useSyncExternalStore(historySearchSession.subscribe, historySearchSession.snapshot);
  useEffect(() => { historySearchSession.bind(permitted); }, [context, context.projectId, permitted]);
  useEffect(() => () => historySearchSession.suspend(), []);
  return { state, session: historySearchSession };
}
