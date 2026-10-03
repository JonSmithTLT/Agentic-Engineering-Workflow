export interface ReadClock {
  manual: boolean;
  now(): Date;
  monotonic(): number;
  visible(): boolean;
  subscribe(listener: () => void): () => void;
}
const realClock: ReadClock = {
  manual: false,
  now: () => new Date(),
  monotonic: () => performance.now(),
  visible: () => document.visibilityState === 'visible',
  subscribe: (listener) => {
    document.addEventListener('visibilitychange', listener);
    return () => document.removeEventListener('visibilitychange', listener);
  },
};
let current: ReadClock = realClock;
const listeners = new Set<() => void>();
export const readClock: ReadClock = {
  get manual() {
    return current.manual;
  },
  now: () => current.now(),
  monotonic: () => current.monotonic(),
  visible: () => current.visible(),
  subscribe(listener) {
    listeners.add(listener);
    document.addEventListener('visibilitychange', listener);
    return () => {
      listeners.delete(listener);
      document.removeEventListener('visibilitychange', listener);
    };
  },
};
export function setReadClock(clock?: ReadClock) {
  current = clock ?? realClock;
  for (const listener of listeners) listener();
}
export function notifyReadClock() {
  for (const listener of listeners) listener();
}
