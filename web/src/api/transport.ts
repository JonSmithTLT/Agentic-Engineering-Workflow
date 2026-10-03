import { z } from 'zod';
import { requestLog, type RequestLog, type RequestTrace } from './diagnostics';
export type Projection<T> = {
  value: T;
  etag?: string;
  last_checked_at: string;
};
export class ReadTransport {
  private cache = new Map<string, Projection<unknown>>();
  constructor(
    private request: typeof fetch = (input, init) =>
      globalThis.fetch(input, init),
    private now = () => new Date(),
    private log: RequestLog = requestLog,
  ) {}
  async get<T>(
    route: string,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
  ): Promise<Projection<T>> {
    if (
      !/^\/(?:project|capabilities|overview|work|runs|evidence|knowledge|history|attention|activity)(?:[/?]|$)/.test(
        route,
      ) ||
      route.includes('\\') ||
      route.includes('#') ||
      new URL(`/api/v1${route}`, 'http://aew.invalid').pathname !==
        `/api/v1${route.split('?')[0]}`
    )
      throw new Error('Invalid API route');
    const prior = this.cache.get(route) as Projection<T> | undefined;
    const headers = new Headers({ Accept: 'application/json' });
    if (prior?.etag) headers.set('If-None-Match', prior.etag);
    const started = performance.now();
    const trace: Omit<RequestTrace, 'id'> = {
      path: `/api/v1${route}`.slice(0, 2048),
      started_at: this.now().toISOString(),
      duration_ms: 0,
      status: null,
      request_etag: prior?.etag?.slice(0, 512),
      validation: [],
    };
    try {
      const response = await this.request(`/api/v1${route}`, {
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
        if (!response.ok)
          throw new Error(`Projection request failed (${response.status})`);
        if (!response.headers.get('Content-Type')?.includes('application/json'))
          throw new Error('Expected a JSON projection');
        const value = schema.parse(await response.json());
        next = {
          value,
          etag: response.headers.get('ETag') ?? undefined,
          last_checked_at: this.now().toISOString(),
        };
      }
      if (signal?.aborted)
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
      this.cache.set(route, next);
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
          field: issue.path.length ? issue.path.map(String).join('.') : '$',
          code: issue.code,
          message: issue.message.slice(0, 512),
        }));
      throw error;
    } finally {
      trace.duration_ms = Math.round((performance.now() - started) * 10) / 10;
      this.log.record(trace);
    }
  }
}
export const transport = new ReadTransport();
