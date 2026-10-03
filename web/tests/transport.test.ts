import { describe, expect, it, vi } from 'vitest';
import { ReadTransport } from '../src/api/transport';
import { responseSchemas } from '../src/api/schema';
import world from '../src/api/mock/fixtures/F1.json';
const payload = world.responses['/overview'];
const json = (value: unknown, etag = '"first"') =>
  new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json', ETag: etag },
  });
describe('read transport', () => {
  it('uses conditional same-origin GET; 304 preserves generation, revision and payload identity', async () => {
    let now = new Date('2026-10-02T12:00:01Z');
    const request = vi
      .fn()
      .mockResolvedValueOnce(json(payload))
      .mockResolvedValueOnce(new Response(null, { status: 304 }));
    const client = new ReadTransport(request, () => now);
    const first = await client.get(
      '/overview',
      responseSchemas.OverviewResponse,
    );
    now = new Date('2026-10-02T12:00:03Z');
    const second = await client.get(
      '/overview',
      responseSchemas.OverviewResponse,
    );
    expect(second.value).toBe(first.value);
    expect(second.value.generated_at).toBe(payload.generated_at);
    expect(second.value.control_revision).toBe(payload.control_revision);
    expect(second.last_checked_at).toBe(now.toISOString());
    const options = request.mock.calls[1][1];
    expect(options.method).toBe('GET');
    expect(options.credentials).toBe('same-origin');
    expect(options.redirect).toBe('error');
    expect(options.headers.get('If-None-Match')).toBe('"first"');
  });
  it('never replaces valid content on malformed or failed refresh', async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce(json(payload))
      .mockResolvedValueOnce(json({ wrong: true }))
      .mockResolvedValueOnce(new Response(null, { status: 500 }))
      .mockResolvedValueOnce(new Response(null, { status: 304 }));
    const client = new ReadTransport(request);
    const first = await client.get(
      '/overview',
      responseSchemas.OverviewResponse,
    );
    await expect(
      client.get('/overview', responseSchemas.OverviewResponse),
    ).rejects.toThrow();
    await expect(
      client.get('/overview', responseSchemas.OverviewResponse),
    ).rejects.toThrow('500');
    expect(
      (await client.get('/overview', responseSchemas.OverviewResponse)).value,
    ).toBe(first.value);
  });
  it('rejects initial 304, non-JSON, redirect/path escape and aborted responses', async () => {
    const client = new ReadTransport(
      vi.fn().mockResolvedValue(new Response(null, { status: 304 })),
    );
    await expect(
      client.get('/overview', responseSchemas.OverviewResponse),
    ).rejects.toThrow('without a cached');
    await expect(
      client.get('//evil.invalid', responseSchemas.OverviewResponse),
    ).rejects.toThrow('Invalid');
    await expect(
      client.get('/work/../overview', responseSchemas.OverviewResponse),
    ).rejects.toThrow('Invalid');
    await expect(
      client.get('/work/%2e%2e/overview', responseSchemas.OverviewResponse),
    ).rejects.toThrow('Invalid');
    const abort = new AbortController();
    abort.abort();
    const wrongType = new ReadTransport(
      vi
        .fn()
        .mockResolvedValue(
          new Response('not json', {
            headers: { 'Content-Type': 'text/html' },
          }),
        ),
    );
    await expect(
      wrongType.get('/overview', responseSchemas.OverviewResponse),
    ).rejects.toThrow('Expected a JSON');
    const aborted = new ReadTransport(vi.fn().mockResolvedValue(json(payload)));
    await expect(
      aborted.get('/overview', responseSchemas.OverviewResponse, abort.signal),
    ).rejects.toThrow('aborted');
  });
});
