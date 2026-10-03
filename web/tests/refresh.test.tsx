import { render, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { installVisibility, useProjection } from '../src/client/queries';
import { transport } from '../src/api/transport';
import { snapshotState, MixedRevisionClock } from '../src/client/freshness';
function hidden(value: boolean) {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: value ? 'hidden' : 'visible',
  });
  document.dispatchEvent(new Event('visibilitychange'));
}
describe('refresh and snapshot states', () => {
  it('distinguishes initial failure, coherent success, mixed success and failed cached refresh', () => {
    expect(snapshotState([], true)).toBe('LOAD ERROR');
    expect(snapshotState([{ revision: 'r1', failed: false }])).toBe('CURRENT');
    expect(
      snapshotState([
        { revision: 'r1', failed: false },
        { revision: 'r2', failed: false },
      ]),
    ).toBe('UPDATING');
    expect(snapshotState([{ revision: 'r1', failed: true }])).toBe(
      'STALE / DISCONNECTED',
    );
  });
  it('warns after 30s visible divergence, pauses hidden, resets on convergence', () => {
    const clock = new MixedRevisionClock();
    expect(clock.sample(true, true, 0)).toBe(false);
    expect(clock.sample(true, true, 15000)).toBe(false);
    expect(clock.sample(true, false, 20000)).toBe(false);
    expect(clock.sample(true, true, 100000)).toBe(false);
    expect(clock.sample(true, true, 109999)).toBe(false);
    expect(clock.sample(true, true, 110000)).toBe(true);
    expect(clock.sample(false, true, 110001)).toBe(false);
    expect(clock.sample(true, true, 150000)).toBe(false);
  });
  it('stops hidden polling and revalidates immediately when visible', async () => {
    hidden(false);
    vi.useFakeTimers();
    const get = vi
      .spyOn(transport, 'get')
      .mockResolvedValue({
        value: { ok: true },
        last_checked_at: '2026-10-02T12:00:00Z',
      });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const dispose = installVisibility(client);
    function Probe() {
      useProjection('/overview', z.object({ ok: z.boolean() }), 'overview');
      return null;
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(get).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2050);
    });
    expect(get.mock.calls.length).toBeGreaterThan(1);
    act(() => hidden(true));
    const count = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(get).toHaveBeenCalledTimes(count);
    await act(async () => {
      hidden(false);
      await vi.advanceTimersByTimeAsync(20);
    });
    expect(get).toHaveBeenCalledTimes(count + 1);
    dispose();
    client.clear();
    hidden(false);
  });
  it('does not request a suppressed capability', async () => {
    hidden(false);
    const get = vi.spyOn(transport, 'get');
    const client = new QueryClient();
    function Probe() {
      const q = useProjection('/queue', z.unknown(), 'list', false);
      return <span>{q.fetchStatus}</span>;
    }
    const { getByText } = render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(getByText('idle')).toBeTruthy());
    expect(get).not.toHaveBeenCalled();
    client.clear();
  });
});
