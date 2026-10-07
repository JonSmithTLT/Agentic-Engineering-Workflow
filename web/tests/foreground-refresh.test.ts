import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { installVisibility } from '../src/client/queries';

function visible(value: boolean) {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: value ? 'visible' : 'hidden' });
  document.dispatchEvent(new Event('visibilitychange'));
}
async function settled() {
  for (let i = 0; i < 10; i++) await Promise.resolve();
}
function fixture() {
  visible(true);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false } } });
  const calls: { aborted: boolean; resolve: () => void }[] = [];
  const subscriptions: (() => void)[] = [];
  function add(id: string, automatic = true, enabled = true) {
    const queryKey = ['projection', id];
    client.setQueryData(queryKey, { value: id });
    const observer = new QueryObserver(client, {
      queryKey, enabled, meta: { automaticRevalidation: automatic },
      queryFn: ({ signal }) => new Promise<{ value: string }>((resolve, reject) => {
        const call = { aborted: false, resolve: () => resolve({ value: id }) };
        calls.push(call);
        signal.addEventListener('abort', () => { call.aborted = true; reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
      }),
    });
    subscriptions.push(observer.subscribe(() => {}));
    return queryKey;
  }
  const key = add('a');
  const dispose = installVisibility(client);
  return { client, calls, key, add, dispose, close: () => { dispose(); subscriptions.forEach(fn => fn()); client.clear(); visible(true); } };
}
it('shares a pending foreground read, then refreshes again after settlement', async () => {
  const f = fixture();
  try {
    visible(true); window.dispatchEvent(new Event('focus'));
    expect(f.calls).toHaveLength(1);
    f.calls[0].resolve(); await settled();
    window.dispatchEvent(new Event('focus'));
    expect(f.calls).toHaveLength(2);
  } finally { f.close(); }
});
for (const leave of ['hidden', 'blur']) it(`a new wake after ${leave} supersedes the old wake without an old finalizer releasing the new one`, async () => {
  const f = fixture();
  try {
    visible(true);
    if (leave === 'hidden') visible(false); else window.dispatchEvent(new Event('blur'));
    visible(true); window.dispatchEvent(new Event('focus'));
    expect(f.calls).toHaveLength(2); expect(f.calls[0].aborted).toBe(true);
    await settled(); window.dispatchEvent(new Event('focus'));
    expect(f.calls).toHaveLength(2);
  } finally { f.close(); }
});
it('first wake supersedes an old manual read and manual refresh still supersedes a wake', async () => {
  const f = fixture();
  try {
    void f.client.refetchQueries({ queryKey: f.key, exact: true });
    visible(true);
    expect(f.calls).toHaveLength(2); expect(f.calls[0].aborted).toBe(true);
    void f.client.refetchQueries({ queryKey: f.key, exact: true });
    expect(f.calls).toHaveLength(3); expect(f.calls[1].aborted).toBe(true);
  } finally { f.close(); }
});
it('new query ownership remains eligible while another query is pending, and excluded queries remain unread', () => {
  const f = fixture();
  try {
    f.add('fixed', false); f.add('concealed', true, false);
    visible(true); expect(f.calls).toHaveLength(1);
    f.add('replacement'); window.dispatchEvent(new Event('focus'));
    expect(f.calls).toHaveLength(2);
    f.dispose(); window.dispatchEvent(new Event('focus')); visible(false); visible(true);
    expect(f.calls).toHaveLength(2);
  } finally { f.close(); }
});
it('replacement query with the same key is not held by retired ownership', async () => {
  const f = fixture();
  try {
    visible(true); expect(f.calls).toHaveLength(1);
    await f.client.cancelQueries(); f.client.removeQueries();
    f.add('a'); window.dispatchEvent(new Event('focus'));
    expect(f.calls).toHaveLength(2); expect(f.calls[0].aborted).toBe(true);
    await settled(); window.dispatchEvent(new Event('focus'));
    expect(f.calls).toHaveLength(2);
  } finally { f.close(); }
});
