import { ReadContext, liveIdentity, type ReadIdentity } from './read-context';
import { readClock } from '../client/clock';
import { z } from 'zod';
import { requestLog, type RequestLog, type RequestTrace } from './diagnostics';
export type Projection<T> = {
  value: T;
  etag?: string;
  last_checked_at: string;
};
export class ProjectionHttpError extends Error {
  constructor(public status: number) {
    super(
      status === 404
        ? 'Not found (404)'
        : status === 401
          ? 'Session required (401)'
          : status === 403
            ? 'Access unavailable (403)'
            : `Projection request failed (${status})`,
    );
    this.name = 'ProjectionHttpError';
  }
}
export function accessRefused(error: unknown) {
  return (
    error instanceof ProjectionHttpError && [401, 403].includes(error.status)
  );
}
export class ReadTransport {
  private cache = new Map<string, Projection<unknown>>();
  context = new ReadContext();
  private listeners = new Set<() => void>();
  private revision = 0;
  snapshot = () => this.revision;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private changed() {
    this.revision++;
    for (const listener of this.listeners) listener();
  }
  reset(identity: ReadIdentity = liveIdentity, notify = true) {
    this.context.retire();
    this.cache.clear();
    this.log.clear();
    this.context = new ReadContext({ ...identity });
    if (notify) this.changed();
  }
  notify() {
    this.changed();
  }
  /** Preview scope refusal invalidates all representations owned by that reader. */
  clearRepresentations() {
    this.cache.clear();
  }
  /** Bounded readers can discard an obsolete page without retiring metadata. */
  forget(route: string) {
    this.cache.delete(JSON.stringify([this.context.key(route), route]));
  }
  constructor(
    private request: typeof fetch = (input, init) => {
      if (import.meta.env.MODE === 'demo' && document.querySelector('meta[name="aew-demo-transport"]')?.getAttribute('content') === 'http') {
        const headers = new Headers(init?.headers);
        const params = new URLSearchParams(location.search);
        headers.set('X-AEW-Demo-Fixture', params.get('fixture') ?? 'F1');
        if (params.get('fault')) headers.set('X-AEW-Demo-Fault', params.get('fault')!);
        return globalThis.fetch(input, { ...init, headers });
      }
      return globalThis.fetch(input, init);
    },
    private now = () => readClock.now(),
    private log: RequestLog = requestLog,
    private policy = {
      base: '/api/v1',
      routes: /^\/(?:project|capabilities|overview|maps|work|runs|evidence|knowledge|history|attention|activity)(?:[/?]|$)/,
    },
  ) {}
  async get<T>(
    route: string,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
  ): Promise<Projection<T>> {
    if (
      !this.policy.routes.test(route) ||
      route.includes('\\') ||
      route.includes('#') ||
      new URL(`${this.policy.base}${route}`, 'http://aew.invalid').pathname !==
        `${this.policy.base}${route.split('?')[0]}`
    )
      throw new Error('Invalid API route');
    const context = this.context;
    if (context.retired)
      throw new DOMException('Request aborted', 'AbortError');
    const key = JSON.stringify([context.key(route), route]);
    const prior = this.cache.get(key) as Projection<T> | undefined;
    const headers = new Headers({ Accept: 'application/json' });
    if (prior?.etag) headers.set('If-None-Match', prior.etag);
    const started = readClock.monotonic();
    const trace: Omit<RequestTrace, 'id'> = {
      path: `${this.policy.base}${route}`.slice(0, 2048),
      context: context.key(route).slice(0, 1024),
      started_at: this.now().toISOString(),
      duration_ms: 0,
      status: null,
      request_etag: prior?.etag?.slice(0, 512),
      validation: [],
    };
    try {
      const response = await this.request(`${this.policy.base}${route}`, {
        method: 'GET',
        credentials: 'same-origin',
        headers,
        signal,
        redirect: 'error',
        cache: 'no-store',
      });
      trace.status = response.status;
      trace.response_etag = response.headers.get('ETag')?.slice(0, 512);
      let next: Projection<T>;
      if (response.status === 304) {
        if (!prior) throw new Error('304 without a cached representation');
        next = { ...prior, last_checked_at: this.now().toISOString() };
      } else {
        if (!response.ok) {
          if ([401, 403].includes(response.status) && !context.retired)
            this.cache.delete(key);
          throw new ProjectionHttpError(response.status);
        }
        if (!response.headers.get('Content-Type')?.includes('application/json'))
          throw new Error('Expected a JSON projection');
        const value = schema.parse(await response.json());
        next = {
          value,
          etag: response.headers.get('ETag') ?? undefined,
          last_checked_at: this.now().toISOString(),
        };
      }
      if (context.retired || this.context !== context || signal?.aborted)
        throw new DOMException('Request aborted', 'AbortError');
      const envelope = next.value as {
        project_id?: unknown;
        control_revision?: unknown;
      };
      if (typeof envelope.project_id === 'string')
        trace.project_id = envelope.project_id.slice(0, 512);
      if (typeof envelope.control_revision === 'string')
        trace.control_revision = envelope.control_revision.slice(0, 512);
      trace.represented_etag = next.etag?.slice(0, 512);
      const previous = prior?.value as typeof envelope | undefined;
      if (
        prior?.etag &&
        next.etag === prior.etag &&
        previous?.project_id === envelope.project_id &&
        previous?.control_revision !== envelope.control_revision
      )
        trace.diagnostic =
          'Browser observation: revision changed while the representation ETag stayed the same.';
      if (
        response.status === 304 &&
        trace.response_etag &&
        trace.response_etag !== trace.request_etag
      )
        trace.diagnostic =
          'Browser observation: 304 returned an ETag different from the requested validator.';
      if (route === '/project' && typeof envelope.project_id === 'string') {
        const wasBound = context.projectId !== undefined;
        context.bind(envelope.project_id);
        if (!wasBound) this.changed();
      } else if (
        context.projectId !== undefined &&
        envelope.project_id !== context.projectId
      ) {
        throw new Error('Projection belongs to a different project');
      }
      this.cache.set(key, next);
      return next;
    } catch (error) {
      trace.error =
        error instanceof z.ZodError
          ? 'Response validation failed'
          : error instanceof SyntaxError
            ? 'Invalid JSON response'
            : error instanceof Error
              ? error.message.slice(0, 512)
              : 'Request failed';
      if (error instanceof z.ZodError)
        trace.validation = error.issues.slice(0, 100).map((issue) => ({
          field: issue.path.length
            ? issue.path.map(String).join('.').slice(0, 2048)
            : '$',
          code: issue.code,
          message: issue.message.slice(0, 512),
        }));
      throw error;
    } finally {
      trace.duration_ms =
        Math.round((readClock.monotonic() - started) * 10) / 10;
      if (!context.retired && this.context === context) this.log.record(trace);
    }
  }
}
export const transport = new ReadTransport();
