import type { z } from 'zod';
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
  ) {}
  async get<T>(
    route: string,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
  ): Promise<Projection<T>> {
    if (
      !/^\/(?:project|capabilities|overview|work|runs|evidence|knowledge|history|queue|attention|activity)(?:[/?]|$)/.test(
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
    const response = await this.request(`/api/v1${route}`, {
      method: 'GET',
      credentials: 'same-origin',
      headers,
      signal,
      redirect: 'error',
      cache: 'no-store',
    });
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
    this.cache.set(route, next);
    return next;
  }
}
export const transport = new ReadTransport();
